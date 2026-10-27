# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

"""A regular payment such as rent, split into dated rows.

The total is split evenly over the payment dates (the last row takes the
rounding difference). Once submitted, every row is posted on its date as a
Journal Entry: debit the expense account, credit the cash or bank account.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_months, flt, fmt_money, get_last_day, getdate, nowdate

from spend.spend.accounting import (
	GL_PRECISION,
	get_fiscal_year,
	get_subtree,
	validate_ledger_account,
	validate_project,
)
from spend.spend.amendment import get_last_paid_date, validate_amendment
from spend.spend.approval import check_approved
from spend.spend.depreciation import FREQUENCY_MONTHS
from spend.spend.doctype.journal_entry.journal_entry import validate_cost_center
from spend.spend.expense_category import get_category_label, get_category_room, validate_category
from spend.spend.notifications import notify_cancelled, notify_recurring_failed, notify_recurring_posted

CUSTOM = "Custom"
VOUCHER_TYPE = "Recurring Payment"


class RecurringPaymentError(frappe.ValidationError):
	pass


class RecurringPayment(Document):
	def validate(self):
		self.title = (self.title or "").strip()
		self.status = "Draft" if self.docstatus == 0 else "Active"
		self.validate_accounts()
		self.validate_dates()
		self.validate_amendment()
		self.set_schedule()
		self.paid_amount = 0
		self.validate_budget()
		self.validate_category_room()

	def validate_accounts(self):
		validate_ledger_account(
			self.expense_account,
			self.company,
			self.meta.get_label("expense_account"),
			root_types=("Expense",),
		)
		label = self.meta.get_label("paid_from")
		validate_ledger_account(self.paid_from, self.company, label, root_types=("Asset",))
		if frappe.db.get_value("Account", self.paid_from, "account_type") not in ("Cash", "Bank"):
			frappe.throw(
				_("{0} {1} must be a Cash or Bank account").format(label, frappe.bold(self.paid_from))
			)

		validate_project(self.project, self.company)
		validate_category(
			self, self.project, self.company, self.expense_account, self.meta.get_label("expense_category")
		)

	def validate_dates(self):
		if getdate(self.to_date) < getdate(self.from_date):
			frappe.throw(_("To Date cannot be before the From Date"), RecurringPaymentError)
		self.total_amount = flt(self.total_amount, GL_PRECISION)
		if self.total_amount <= 0:
			frappe.throw(_("Total Amount must be greater than zero"), RecurringPaymentError)

	def validate_budget(self):
		"""The payment is taken from a Budget: directly, or from the share of its project."""
		if self.project:
			self.budget = frappe.db.get_value("Project", self.project, "budget")
			if not self.budget:
				frappe.throw(_("Project {0} has no Budget").format(frappe.bold(self.project)))
		if not self.budget:
			return  # the mandatory check asks for it
		budget = frappe.get_doc("Budget", self.budget)
		if self.has_value_changed("budget"):
			if budget.docstatus != 1:
				frappe.throw(_("Budget {0} is not submitted").format(frappe.bold(self.budget)))
			if budget.company != self.company:
				frappe.throw(_("Budget {0} belongs to another company").format(frappe.bold(self.budget)))
		if self.expense_account not in {r.account for r in budget.accounts}:
			frappe.throw(
				_("Expense account {0} is not on Budget {1}").format(
					frappe.bold(self.expense_account), self.budget
				)
			)
		self.set_cost_center(budget)
		self.validate_budget_year(budget)
		self.validate_budget_room(budget)

	def set_cost_center(self, budget):
		"""The project's cost center, the Budget's when it is not a group, or the company default."""
		allowed = get_subtree("Cost Center", budget.cost_center)
		if not self.cost_center and self.project:
			self.cost_center = frappe.db.get_value("Project", self.project, "cost_center")
		if not self.cost_center and not frappe.db.get_value("Cost Center", budget.cost_center, "is_group"):
			self.cost_center = budget.cost_center
		if not self.cost_center:
			default = frappe.get_cached_value("Company", self.company, "default_cost_center")
			self.cost_center = default if default in allowed else None
		if not self.cost_center or self.cost_center not in allowed:
			frappe.throw(
				_("Pick a cost center under {0}, the cost center of Budget {1}").format(
					frappe.bold(budget.cost_center), self.budget
				)
			)
		validate_cost_center(self.cost_center, self.company)

	def validate_budget_year(self, budget):
		start, end = frappe.db.get_value("Fiscal Year", budget.fiscal_year, ["start_date", "end_date"])
		if getdate(self.from_date) < getdate(start) or getdate(self.to_date) > getdate(end):
			frappe.throw(
				_("Budget {0} is for {1}, {2} to {3}. Keep the payment dates in that year.").format(
					self.budget,
					budget.fiscal_year,
					frappe.format(start, "Date"),
					frappe.format(end, "Date"),
				),
				RecurringPaymentError,
			)

	def validate_budget_room(self, budget):
		"""Without a project the payment takes what the Budget has free, with one what the project's share has."""
		from spend.spend.doctype.project.project import (
			add_allocation,
			format_shortfalls,
			get_allocations,
			get_project_allocations,
			get_project_shortfalls,
			get_shortfalls,
			has_share,
			make_recurring_holder,
		)

		holder = make_recurring_holder(self, flt(self.total_amount, GL_PRECISION))
		if self.project and has_share(frappe.get_doc("Project", self.project)):
			allocations = get_project_allocations(self.project, exclude=self.name)
			add_allocation(allocations, holder)
			shortfalls = get_project_shortfalls(frappe.get_doc("Project", self.project), allocations)
			source = _("the share of Project {0}").format(self.project)
		else:
			allocations = get_allocations(self.budget, exclude=self.name)
			add_allocation(allocations, holder)
			shortfalls = get_shortfalls(budget, allocations)
			source = _("Budget {0}").format(self.budget)
		if shortfalls:
			frappe.throw(
				_("Recurring Payment {0} does not fit in {1}:").format(frappe.bold(self.title), source)
				+ "<br>"
				+ format_shortfalls(shortfalls, self.currency),
				title=_("Over the Budget"),
			)

	def validate_category_room(self):
		"""The payment must fit in what is left of the category budgets of its project."""
		if not (self.project and self.expense_category):
			return
		project = frappe.db.get_value(
			"Project", self.project, ["project_name", "action_if_exceeded"], as_dict=True
		)
		if project.action_if_exceeded == "Ignore":
			return
		for row, free in get_category_room(
			self.project, self.expense_category, self.expense_sub_category, exclude=self.name
		):
			if self.total_amount <= free:
				continue
			message = _(
				"Recurring Payment {0} needs {1}, but category {2} of Project {3} has {4} free."
			).format(
				frappe.bold(self.title),
				fmt_money(self.total_amount, currency=self.currency),
				frappe.bold(get_category_label(row)),
				frappe.bold(project.project_name),
				fmt_money(free, currency=self.currency),
			)
			if project.action_if_exceeded == "Stop":
				frappe.throw(message, title=_("Over the Category Budget"))
			frappe.msgprint(message, indicator="orange", title=_("Over the Category Budget"))

	def validate_amendment(self):
		"""An amendment pays only what earlier versions did not, so it starts after their last payment."""
		validate_amendment(self)
		if not self.amended_from:
			return
		last_paid = get_last_paid_date(self.doctype, self.amended_from)
		if last_paid and getdate(self.from_date) <= last_paid:
			frappe.throw(
				_("{0} already paid up to {1}. Start this amendment after that date.").format(
					self.amended_from, frappe.format(last_paid, "Date")
				),
				RecurringPaymentError,
			)

	def set_schedule(self):
		if self.frequency == CUSTOM:
			rows = get_custom_schedule(
				[(r.payment_date, r.amount) for r in self.schedule],
				self.from_date,
				self.to_date,
				self.total_amount,
			)
		else:
			rows = get_schedule(self.from_date, self.to_date, self.frequency, self.total_amount)
		if not rows:
			frappe.throw(_("The schedule has no payment dates"), RecurringPaymentError)
		self.set("schedule", rows)
		self.warn_missing_fiscal_years()

	def warn_missing_fiscal_years(self):
		"""Dates without a fiscal year are posted once that year is created."""
		missing = [r.payment_date for r in self.schedule if not get_fiscal_year(r.payment_date, throw=False)]
		if missing:
			frappe.msgprint(
				_("No fiscal year covers {0} payments, from {1}. Create the fiscal year before then.").format(
					len(missing), frappe.format(min(missing), "Date")
				),
				indicator="orange",
				alert=True,
			)

	def before_submit(self):
		check_approved(self)
		# one at a time per Budget, so two payments cannot both take what is left
		frappe.db.get_value("Budget", self.budget, "name", for_update=True)
		self.validate_budget_room(frappe.get_doc("Budget", self.budget))

	def on_submit(self):
		self.db_set("status", "Active")
		make_payment_entries(self.name, nowdate())
		self.reload()

	def before_cancel(self):
		# posted entries are real payments: they stay, linked to this cancelled version
		self.ignore_linked_doctypes = ("Journal Entry", "GL Entry")

	def on_cancel(self):
		self.db_set("status", "Cancelled")
		notify_cancelled(self, _("No more payments will be posted from it."))


# ---------------------------------------------------------------- schedule maths (pure)


def get_payment_dates(from_date, to_date, frequency: str) -> list:
	"""Dates from `from_date` every period up to `to_date`. A month-end start keeps month ends."""
	if frequency not in FREQUENCY_MONTHS:
		frappe.throw(_("Unsupported frequency {0}").format(frequency), RecurringPaymentError)
	start, end = getdate(from_date), getdate(to_date)
	month_end = start == get_last_day(start)
	step = FREQUENCY_MONTHS[frequency]
	dates = []
	while True:
		date = add_months(start, len(dates) * step)
		date = get_last_day(date) if month_end else getdate(date)
		if date > end:
			return dates
		dates.append(date)


def split_amount(total: float, count: int) -> list[float]:
	"""Even split; the last share takes whatever rounding leaves over."""
	if count <= 0:
		return []
	share = flt(flt(total) / count, GL_PRECISION)
	return [share] * (count - 1) + [flt(flt(total) - share * (count - 1), GL_PRECISION)]


def get_schedule(from_date, to_date, frequency: str, total: float) -> list[dict]:
	dates = get_payment_dates(from_date, to_date, frequency)
	return [
		{"payment_date": d, "amount": a} for d, a in zip(dates, split_amount(total, len(dates)), strict=True)
	]


def get_custom_schedule(rows: list, from_date, to_date, total: float) -> list[dict]:
	"""Dates entered by hand. Blank amounts everywhere means an even split;
	otherwise the amounts must add up to the total."""
	start, end = getdate(from_date), getdate(to_date)
	seen = set()
	for i, (date, _amount) in enumerate(rows, 1):
		if not date:
			frappe.throw(_("Row {0}: Payment Date is required").format(i), RecurringPaymentError)
		date = getdate(date)
		if not start <= date <= end:
			frappe.throw(
				_("Row {0}: {1} is outside the From and To dates").format(i, frappe.format(date, "Date")),
				RecurringPaymentError,
			)
		if date in seen:
			frappe.throw(
				_("Row {0}: {1} is repeated").format(i, frappe.format(date, "Date")), RecurringPaymentError
			)
		seen.add(date)

	rows = sorted(((getdate(d), flt(a, GL_PRECISION)) for d, a in rows), key=lambda r: r[0])
	if not any(a for _d, a in rows):
		amounts = split_amount(total, len(rows))
	else:
		amounts = [a for _d, a in rows]
		if any(a <= 0 for a in amounts):
			frappe.throw(_("Every amount must be greater than zero"), RecurringPaymentError)
		allotted = flt(sum(amounts), GL_PRECISION)
		if abs(allotted - flt(total, GL_PRECISION)) >= 0.01:
			frappe.throw(
				_("The amounts add up to {0}, not the Total Amount {1}").format(
					allotted, flt(total, GL_PRECISION)
				),
				RecurringPaymentError,
			)
	return [{"payment_date": d, "amount": a} for (d, _a), a in zip(rows, amounts, strict=True)]


@frappe.whitelist()
def preview_schedule(
	from_date: str, to_date: str, frequency: str, total_amount: float, dates: list | str | None = None
) -> list[dict]:
	"""The split the server will save, for the New page."""
	if not (from_date and to_date) or getdate(to_date) < getdate(from_date) or flt(total_amount) <= 0:
		return []
	if frequency == CUSTOM:
		dates = frappe.parse_json(dates) if isinstance(dates, str) else dates or []
		return get_custom_schedule([(d, 0) for d in dates if d], from_date, to_date, total_amount)
	return get_schedule(from_date, to_date, frequency, total_amount)


@frappe.whitelist()
def get_recurring_room(budget: str | None = None, project: str | None = None) -> dict | None:
	"""What a recurring payment can take: what is left of the project's share, or what its Budget has free."""
	from spend.spend.doctype.project.project import get_allocations, get_project_allocations, has_share

	share = False
	if project:
		project_doc = frappe.get_doc("Project", project)
		project_doc.check_permission("read")
		budget = project_doc.budget
		share = has_share(project_doc)
	if not budget:
		return None
	doc = frappe.get_doc("Budget", budget)
	doc.check_permission("read")

	if share:
		allocations = get_project_allocations(project)
		shares = {r.account: flt(r.budget_amount, GL_PRECISION) for r in project_doc.budget_accounts}
		limits = shares or dict.fromkeys((r.account for r in doc.accounts), None)
		total = (
			flt(project_doc.budget_amount, GL_PRECISION) if project_doc.budget_amount or not shares else None
		)
	else:
		allocations = get_allocations(budget)
		limits = {r.account: flt(r.budget_amount, GL_PRECISION) for r in doc.accounts}
		total = flt(doc.total_budget, GL_PRECISION)

	def free(limit, held):
		return None if limit is None else flt(limit - held, GL_PRECISION)

	start, end = frappe.db.get_value("Fiscal Year", doc.fiscal_year, ["start_date", "end_date"])
	cost_center = frappe.db.get_value(
		"Cost Center", doc.cost_center, ["is_group as cost_center_is_group", "lft", "rgt"], as_dict=True
	)
	default_cost_center = project_doc.cost_center if project else None
	if not default_cost_center and not cost_center.cost_center_is_group:
		default_cost_center = doc.cost_center
	held = allocations["total"]
	return {
		"budget": doc.name,
		"project": project,
		"share": share,
		"fiscal_year": doc.fiscal_year,
		"year_start": start,
		"year_end": end,
		"cost_center": doc.cost_center,
		**cost_center,
		"default_cost_center": default_cost_center,
		"currency": doc.currency,
		"accounts": [
			{
				"account": account,
				"limit": limit,
				"held": allocations["accounts"].get(account, 0.0),
				"free": free(limit, allocations["accounts"].get(account, 0.0)),
			}
			for account, limit in limits.items()
		],
		"total": total,
		"held": held,
		"free": free(total, held),
	}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_recurring_accounts(doctype, txt, searchfield, start, page_len, filters):
	"""Account search in Desk: the project's share accounts, or the Budget's accounts."""
	room = get_recurring_room(filters.get("budget"), filters.get("project"))
	if not room:
		return []
	accounts = [[r["account"]] for r in room["accounts"] if (txt or "").lower() in r["account"].lower()]
	return accounts[int(start) : int(start) + int(page_len)]


# ---------------------------------------------------------------- postings


def post_recurring_payments_daily():
	"""Scheduler entry point: post every due row, committing per recurring payment."""
	for name in get_payments_with_due_rows(nowdate()):
		try:
			make_payment_entries(name, nowdate())
			frappe.db.commit()  # nosemgrep: one payment's failure must not roll back the others
		except Exception as e:
			frappe.db.rollback()
			frappe.log_error(title=_("Recurring payment posting failed for {0}").format(name))
			notify_recurring_failed(name, str(e))
			frappe.db.commit()  # nosemgrep: keep the error log and the alert


def get_payments_with_due_rows(date, company: str | None = None) -> list[str]:
	rp = frappe.qb.DocType("Recurring Payment")
	row = frappe.qb.DocType("Recurring Payment Schedule")
	query = (
		frappe.qb.from_(rp)
		.join(row)
		.on(row.parent == rp.name)
		.select(rp.name)
		.distinct()
		.where(
			(rp.docstatus == 1)
			& (rp.status == "Active")
			& (row.payment_date <= getdate(date))
			& ((row.journal_entry.isnull()) | (row.journal_entry == ""))
		)
	)
	if company:
		query = query.where(rp.company == company)
	return query.run(pluck=True)


def make_payment_entries(name: str, date=None) -> list[str]:
	"""Post every unposted row due on or before `date`, oldest first."""
	date = getdate(date or nowdate())
	# serialise postings per document so concurrent runs cannot double-post a row
	frappe.db.get_value("Recurring Payment", name, "name", for_update=True)
	doc = frappe.get_doc("Recurring Payment", name)
	if doc.docstatus != 1 or doc.status == "Stopped":
		frappe.throw(_("Recurring Payment {0} is not active").format(name), RecurringPaymentError)

	posted = []
	for row in sorted(doc.schedule, key=lambda r: getdate(r.payment_date)):
		if row.journal_entry:
			continue
		if getdate(row.payment_date) > date:
			break
		# re-read under the lock: another worker may have posted it meanwhile
		if frappe.db.get_value("Recurring Payment Schedule", row.name, "journal_entry"):
			continue
		posted.append(make_payment_entry(doc, row))
	notify_recurring_posted(doc, posted)
	return posted


def make_payment_entry(doc, row) -> str:
	remark = _("{0} for {1}").format(doc.title, frappe.format(row.payment_date, "Date"))
	if doc.payee:
		remark += " · " + _("paid to {0}").format(doc.payee)
	je = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": VOUCHER_TYPE,
			"company": doc.company,
			"posting_date": row.payment_date,
			"title": doc.title,
			"user_remark": remark,
			"recurring_payment": doc.name,
			"recurring_payment_row": row.name,
			"accounts": [
				{
					"account": doc.expense_account,
					"cost_center": doc.cost_center,
					"project": doc.project,
					"expense_category": doc.expense_category,
					"expense_sub_category": doc.expense_sub_category,
					"debit": row.amount,
				},
				{"account": doc.paid_from, "project": doc.project, "credit": row.amount},
			],
		}
	)
	je.flags.ignore_permissions = True
	je.insert()
	je.submit()
	return je.name


def validate_recurring_reference(je):
	"""Called from Journal Entry.validate."""
	if je.voucher_type != VOUCHER_TYPE:
		if je.recurring_payment or je.recurring_payment_row:
			frappe.throw(_("Only Recurring Payment entries can reference a recurring payment"))
		return
	if not (je.recurring_payment and je.recurring_payment_row):
		frappe.throw(_("Recurring Payment entries are created from a Recurring Payment"))

	row = frappe.db.get_value(
		"Recurring Payment Schedule", je.recurring_payment_row, ["parent", "journal_entry"], as_dict=True
	)
	if not row or row.parent != je.recurring_payment:
		frappe.throw(_("Schedule row does not belong to {0}").format(je.recurring_payment))
	if frappe.db.get_value("Recurring Payment", je.recurring_payment, "docstatus") != 1:
		frappe.throw(_("Recurring Payment {0} is not active").format(je.recurring_payment))
	duplicate = row.journal_entry if row.journal_entry != je.name else None
	duplicate = duplicate or frappe.db.get_value(
		"Journal Entry",
		{"recurring_payment_row": je.recurring_payment_row, "docstatus": 1, "name": ("!=", je.name)},
	)
	if duplicate:
		frappe.throw(
			_("This payment is already posted in {0}").format(frappe.bold(duplicate)), RecurringPaymentError
		)


def on_recurring_entry_submit(je):
	frappe.db.set_value("Recurring Payment Schedule", je.recurring_payment_row, "journal_entry", je.name)
	update_status(je.recurring_payment)


def on_recurring_entry_cancel(je):
	"""Free the row so it is posted again; the cancelled entry and its GL stay."""
	if (
		frappe.db.get_value("Recurring Payment Schedule", je.recurring_payment_row, "journal_entry")
		== je.name
	):
		frappe.db.set_value("Recurring Payment Schedule", je.recurring_payment_row, "journal_entry", None)
	update_status(je.recurring_payment)


def update_status(name: str):
	doc = frappe.get_doc("Recurring Payment", name)
	if doc.docstatus != 1:
		return
	posted = [r for r in doc.schedule if r.journal_entry]
	values = {"paid_amount": flt(sum(flt(r.amount) for r in posted), GL_PRECISION)}
	if len(posted) == len(doc.schedule):
		values["status"] = "Completed"
	elif doc.status != "Stopped":
		values["status"] = "Active"
	doc.db_set(values)


# ---------------------------------------------------------------- actions


def get_submitted(name: str):
	doc = frappe.get_doc("Recurring Payment", name)
	doc.check_permission("submit")
	if doc.docstatus != 1:
		frappe.throw(_("Submit Recurring Payment {0} first").format(name), RecurringPaymentError)
	return doc


@frappe.whitelist()
def post_due_payments(name: str) -> list[str]:
	"""Post every row due today or earlier now, instead of waiting for the daily job."""
	get_submitted(name)
	return make_payment_entries(name, nowdate())


@frappe.whitelist()
def stop(name: str):
	"""Rows not yet posted are skipped until it is resumed."""
	doc = get_submitted(name)
	if doc.status != "Active":
		frappe.throw(_("Only an active recurring payment can be stopped"), RecurringPaymentError)
	doc.db_set("status", "Stopped")


@frappe.whitelist()
def resume(name: str):
	doc = get_submitted(name)
	if doc.status != "Stopped":
		frappe.throw(_("Recurring Payment {0} is not stopped").format(name), RecurringPaymentError)
	doc.db_set("status", "Active")
	update_status(name)


# ---------------------------------------------------------------- lists


def get_recurring_rows(filters: dict, limit: int = 500) -> list[dict]:
	"""Recurring payments with their next unposted date and what is left to pay."""
	docs = frappe.get_list(
		"Recurring Payment",
		filters={"docstatus": ("<", 2), **filters},
		fields=[
			"name",
			"title",
			"payee",
			"status",
			"expense_account",
			"cost_center",
			"project",
			"frequency",
			"from_date",
			"to_date",
			"total_amount",
			"paid_amount",
			"docstatus",
		],
		order_by="creation desc",
		limit=limit,
	)
	if not docs:
		return []

	row = frappe.qb.DocType("Recurring Payment Schedule")
	pending = (
		frappe.qb.from_(row)
		.select(row.parent, row.payment_date, row.amount)
		.where(
			row.parent.isin([d.name for d in docs])
			& ((row.journal_entry.isnull()) | (row.journal_entry == ""))
		)
		.orderby(row.payment_date)
		.run(as_dict=True)
	)
	next_row = {}
	for r in pending:
		next_row.setdefault(r.parent, r)
	for doc in docs:
		upcoming = next_row.get(doc.name)
		doc.next_date = upcoming.payment_date if upcoming else None
		doc.next_amount = flt(upcoming.amount) if upcoming else 0.0
		doc.remaining = flt(flt(doc.total_amount) - flt(doc.paid_amount), GL_PRECISION)
	return docs


def get_upcoming_payments(company: str, days: int = 30) -> list[dict]:
	"""Unposted rows of active recurring payments due within `days` (overdue ones included)."""
	rp = frappe.qb.DocType("Recurring Payment")
	row = frappe.qb.DocType("Recurring Payment Schedule")
	until = frappe.utils.add_days(nowdate(), days)
	return (
		frappe.qb.from_(rp)
		.join(row)
		.on(row.parent == rp.name)
		.select(rp.name, rp.title, rp.payee, rp.project, row.payment_date, row.amount)
		.where(
			(rp.company == company)
			& (rp.docstatus == 1)
			& (rp.status == "Active")
			& (row.payment_date <= until)
			& ((row.journal_entry.isnull()) | (row.journal_entry == ""))
		)
		.orderby(row.payment_date)
		.limit(8)
		.run(as_dict=True)
	)
