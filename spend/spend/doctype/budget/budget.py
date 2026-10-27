# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt, fmt_money, get_last_day, getdate

from spend.spend.accounting import (
	GL_PRECISION,
	get_ancestors_with_self,
	get_balance,
	get_subtree,
	validate_company_link,
	validate_ledger_account,
)
from spend.spend.amendment import validate_amendment


class BudgetExceededError(frappe.ValidationError):
	pass


class DuplicateBudgetError(frappe.ValidationError):
	pass


class Budget(Document):
	def validate(self):
		validate_amendment(self)
		self.validate_cost_center()
		self.validate_accounts()
		self.validate_duplicate()
		self.total_budget = flt(sum(flt(r.budget_amount) for r in self.accounts), GL_PRECISION)
		if self.budget_period == "Monthly":
			if not self.monthly_distribution:
				self.set_even_distribution()
			self.validate_distribution()
		else:
			self.monthly_distribution = []
		if self.docstatus == 0:
			self.validate_project_shares(throw=False)

	def before_submit(self):
		from spend.spend.approval import check_approved

		check_approved(self)
		self.validate_duplicate()
		self.validate_project_shares(throw=True)

	def on_submit(self):
		self.move_holders()

	def validate_project_shares(self, throw: bool):
		"""An amendment must still hold what the projects and recurring payments of the cancelled version took."""
		from spend.spend.doctype.project.project import get_allocations, get_shortfalls

		if not self.amended_from:
			return
		allocations = get_allocations(self.amended_from)
		shortfalls = get_shortfalls(self, allocations) if allocations["holders"] else []
		if not shortfalls:
			return
		message = (
			_("Projects and recurring payments on {0} hold more than this amendment gives:").format(
				self.amended_from
			)
			+ "<br>"
			+ "<br>".join(
				_("{0}: they hold {1}, the amendment gives {2} ({3})").format(
					s.label,
					fmt_money(s.held, currency=self.currency),
					fmt_money(s.available, currency=self.currency),
					s.holders,
				)
				for s in shortfalls
			)
			+ "<br>"
			+ _("Lower these first.")
		)
		if throw:
			frappe.throw(message, title=_("Over the Amendment"))
		frappe.msgprint(message, indicator="orange", title=_("Over the Amendment"))

	def move_holders(self):
		"""Projects and recurring payments follow the Budget to its approved amendment."""
		if not self.amended_from:
			return
		for doctype in ("Project", "Recurring Payment"):
			for name in frappe.get_all(doctype, filters={"budget": self.amended_from}, pluck="name"):
				doc = frappe.get_doc(doctype, name)
				doc.db_set("budget", self.name)
				doc.add_comment(
					"Info",
					_("Moved from Budget {0} to its amendment {1}").format(self.amended_from, self.name),
				)

	def before_cancel(self):
		# its recurring payments move to the amendment once that is approved
		self.ignore_linked_doctypes = ("Recurring Payment",)

	def on_cancel(self):
		from spend.spend.notifications import notify_cancelled

		notify_cancelled(
			self,
			_("Expense checks for {0} stop until an amendment is approved.").format(self.cost_center),
		)

	def validate_cost_center(self):
		validate_company_link("Cost Center", self.cost_center, self.company)
		if frappe.db.get_value("Cost Center", self.cost_center, "disabled"):
			frappe.throw(_("Cost Center {0} is disabled").format(frappe.bold(self.cost_center)))
		if frappe.db.get_value("Fiscal Year", self.fiscal_year, "disabled"):
			frappe.throw(_("Fiscal Year {0} is disabled").format(frappe.bold(self.fiscal_year)))

	def validate_accounts(self):
		seen = set()
		for row in self.accounts:
			validate_ledger_account(
				row.account, self.company, _("Row {0}: Account").format(row.idx), root_types=("Expense",)
			)
			if row.account in seen:
				frappe.throw(_("Row {0}: Account {1} is repeated").format(row.idx, frappe.bold(row.account)))
			seen.add(row.account)
			if flt(row.budget_amount) <= 0:
				frappe.throw(_("Row {0}: Budget amount must be greater than zero").format(row.idx))

	def validate_duplicate(self):
		budget_account = frappe.qb.DocType("Budget Account")
		budget = frappe.qb.DocType("Budget")
		accounts = [r.account for r in self.accounts]
		if not accounts:
			return
		existing = (
			frappe.qb.from_(budget)
			.join(budget_account)
			.on(budget_account.parent == budget.name)
			.select(budget.name, budget_account.account)
			.where(
				(budget.docstatus == 1)
				& (budget.name != (self.name or ""))
				& (budget.company == self.company)
				& (budget.fiscal_year == self.fiscal_year)
				& (budget.cost_center == self.cost_center)
				& (budget_account.account.isin(accounts))
			)
			.limit(1)
			.run(as_dict=True)
		)
		if existing:
			frappe.throw(
				_("Budget {0} already covers account {1} for {2} in {3}").format(
					frappe.bold(existing[0].name),
					frappe.bold(existing[0].account),
					frappe.bold(self.cost_center),
					self.fiscal_year,
				),
				DuplicateBudgetError,
			)

	def set_even_distribution(self):
		periods = get_fiscal_year_months(self.fiscal_year)
		share = flt(100 / len(periods), 9)
		self.monthly_distribution = []
		for i, (period_name, from_date, to_date) in enumerate(periods):
			percentage = share if i < len(periods) - 1 else flt(100 - share * (len(periods) - 1), 9)
			self.append(
				"monthly_distribution",
				{
					"period_name": period_name,
					"from_date": from_date,
					"to_date": to_date,
					"percentage": percentage,
				},
			)

	def validate_distribution(self):
		start, end = frappe.db.get_value("Fiscal Year", self.fiscal_year, ["start_date", "end_date"])
		for row in self.monthly_distribution:
			if getdate(row.from_date) < getdate(start) or getdate(row.to_date) > getdate(end):
				frappe.throw(
					_("Row {0}: Period must be within Fiscal Year {1}").format(row.idx, self.fiscal_year)
				)
			if flt(row.percentage) < 0:
				frappe.throw(_("Row {0}: Allocation cannot be negative").format(row.idx))
		total = sum(flt(r.percentage) for r in self.monthly_distribution)
		if abs(total - 100) > 0.01:
			frappe.throw(_("Monthly distribution must add up to 100% (currently {0}%)").format(flt(total, 2)))

	def get_period(self, date) -> tuple:
		"""Return (from_date, to_date, share) of the budget period containing `date`."""
		if self.budget_period == "Monthly":
			date = getdate(date)
			for row in self.monthly_distribution:
				if getdate(row.from_date) <= date <= getdate(row.to_date):
					return getdate(row.from_date), getdate(row.to_date), flt(row.percentage) / 100
		start, end = frappe.db.get_value("Fiscal Year", self.fiscal_year, ["start_date", "end_date"])
		return getdate(start), getdate(end), 1.0

	def get_budget_vs_actual(self, to_date=None) -> list[dict]:
		"""Allocated, actual, remaining and utilization for each account over the fiscal year."""
		start, end = frappe.db.get_value("Fiscal Year", self.fiscal_year, ["start_date", "end_date"])
		rows = []
		for row in self.accounts:
			actual = get_balance(
				account=row.account,
				cost_center=self.cost_center,
				company=self.company,
				from_date=start,
				to_date=min(getdate(to_date), getdate(end)) if to_date else end,
			)
			rows.append(make_variance_row(row.account, flt(row.budget_amount), actual))
		return rows

	def get_monthly_budget_vs_actual(self) -> list[dict]:
		periods = (
			[
				(r.period_name, r.from_date, r.to_date, flt(r.percentage) / 100)
				for r in self.monthly_distribution
			]
			if self.budget_period == "Monthly"
			else [(p[0], p[1], p[2], None) for p in get_fiscal_year_months(self.fiscal_year)]
		)
		out = []
		for period_name, from_date, to_date, share in periods:
			for row in self.accounts:
				allocated = (
					flt(row.budget_amount) * share
					if share is not None
					else flt(row.budget_amount) / len(periods)
				)
				actual = get_balance(
					account=row.account,
					cost_center=self.cost_center,
					company=self.company,
					from_date=from_date,
					to_date=to_date,
				)
				out.append(
					{
						"period": period_name,
						"from_date": from_date,
						"to_date": to_date,
						**make_variance_row(row.account, flt(allocated, GL_PRECISION), actual),
					}
				)
		return out


def make_variance_row(account: str, allocated: float, actual: float) -> dict:
	return {
		"account": account,
		"budget": flt(allocated, GL_PRECISION),
		"actual": flt(actual, GL_PRECISION),
		"remaining": flt(allocated - actual, GL_PRECISION),
		"utilization": flt(actual / allocated * 100, 2) if allocated else 0,
	}


def get_fiscal_year_months(fiscal_year: str) -> list[tuple]:
	start, end = frappe.db.get_value("Fiscal Year", fiscal_year, ["start_date", "end_date"])
	start, end = getdate(start), getdate(end)
	periods, current = [], start
	while current <= end:
		period_end = min(get_last_day(current), end)
		periods.append((current.strftime("%b %Y"), current, period_end))
		current = add_days(period_end, 1)
	return periods


def validate_expense_against_budget(doc, lines: list[tuple] | None = None):
	"""Check expense postings of a voucher against submitted budgets.

	`lines` are (account, cost_center, amount) tuples; they default to the
	rows of a Journal Entry. Budgets on a cost center apply to its descendants
	too. `Stop` blocks the voucher, `Warn` shows a message. Depreciation is
	non-discretionary, so it is never blocked, only warned.
	"""
	if lines is None:
		lines = [(r.account, r.cost_center, flt(r.debit) - flt(r.credit)) for r in doc.accounts]

	amounts = {}
	for account, cost_center, amount in lines:
		if not cost_center:
			continue
		if frappe.db.get_value("Account", account, "root_type") != "Expense":
			continue
		key = (account, cost_center)
		amounts[key] = amounts.get(key, 0) + flt(amount)

	for (account, cost_center), amount in amounts.items():
		if amount <= 0:
			continue
		for budget_name in get_applicable_budgets(doc, account, cost_center):
			check_budget(budget_name, account, doc, amounts)


def get_applicable_budgets(doc, account: str, cost_center: str) -> list[str]:
	budget = frappe.qb.DocType("Budget")
	budget_account = frappe.qb.DocType("Budget Account")
	return (
		frappe.qb.from_(budget)
		.join(budget_account)
		.on(budget_account.parent == budget.name)
		.select(budget.name)
		.distinct()
		.where(
			(budget.docstatus == 1)
			& (budget.company == doc.company)
			& (budget.fiscal_year == doc.fiscal_year)
			& (budget.action_if_exceeded != "Ignore")
			& (budget.cost_center.isin(get_ancestors_with_self("Cost Center", cost_center)))
			& (budget_account.account == account)
		)
		.run(pluck=True)
	)


def check_budget(budget_name: str, account: str, doc, amounts: dict):
	budget = frappe.get_doc("Budget", budget_name)
	annual = next(flt(r.budget_amount) for r in budget.accounts if r.account == account)
	from_date, to_date, share = budget.get_period(doc.posting_date)
	allocated = flt(annual * share, GL_PRECISION)

	covered = set(get_subtree("Cost Center", budget.cost_center))
	pending = sum(amt for (acc, cc), amt in amounts.items() if acc == account and cc in covered)
	actual = get_balance(
		account=account,
		cost_center=budget.cost_center,
		company=budget.company,
		from_date=from_date,
		to_date=to_date,
	)
	total = flt(actual + pending, GL_PRECISION)
	if total <= allocated:
		return

	currency = budget.currency
	message = _(
		"{0} budget for account {1} against cost center {2} is {3}. It will be exceeded by {4} (spent {5})."
	).format(
		_("Monthly") if budget.budget_period == "Monthly" else _("Annual"),
		frappe.bold(account),
		frappe.bold(budget.cost_center),
		fmt_money(allocated, currency=currency),
		frappe.bold(fmt_money(total - allocated, currency=currency)),
		fmt_money(total, currency=currency),
	)
	if budget.action_if_exceeded == "Stop" and doc.get("voucher_type") != "Depreciation Entry":
		frappe.throw(message, BudgetExceededError, title=_("Budget Exceeded"))
	frappe.msgprint(message, indicator="orange", title=_("Budget Exceeded"))


@frappe.whitelist()
def get_budget_summary(budget: str) -> dict:
	doc = frappe.get_doc("Budget", budget)
	doc.check_permission("read")
	rows = doc.get_budget_vs_actual()
	allocated = sum(r["budget"] for r in rows)
	actual = sum(r["actual"] for r in rows)
	return {
		"rows": rows,
		"allocated": flt(allocated, GL_PRECISION),
		"actual": flt(actual, GL_PRECISION),
		"remaining": flt(allocated - actual, GL_PRECISION),
		"utilization": flt(actual / allocated * 100, 2) if allocated else 0,
		"periods": doc.get_monthly_budget_vs_actual(),
		"currency": doc.currency,
	}


def validate_project_budget(doc, lines: list[tuple]):
	"""Check expense postings of a voucher against the lifetime budget of their projects.

	`lines` are (account, project, amount) tuples. A project can limit its total
	spend and the spend on single expense accounts; both are checked.
	"""
	from spend.spend.doctype.project.project import get_project_spent

	pending = {}
	for account, project, amount in lines:
		if not project or frappe.db.get_value("Account", account, "root_type") != "Expense":
			continue
		amounts = pending.setdefault(project, {})
		amounts[account] = amounts.get(account, 0) + flt(amount)

	for project_name, amounts in pending.items():
		project = frappe.get_doc("Project", project_name)
		if project.action_if_exceeded == "Ignore":
			continue

		checks = []
		if flt(project.budget_amount) > 0:
			checks.append((None, flt(project.budget_amount), sum(amounts.values())))
		for row in project.budget_accounts:
			covered = set(get_subtree("Account", row.account))
			checks.append(
				(row.account, flt(row.budget_amount), sum(a for acc, a in amounts.items() if acc in covered))
			)

		for account, allocated, amount in checks:
			if amount <= 0:
				continue
			spent = get_project_spent(project.name, account)
			total = flt(spent + amount, GL_PRECISION)
			if total <= allocated:
				continue
			currency = project.currency or doc.get("currency")
			scope = (
				_("Budget for account {0} on project {1}").format(
					frappe.bold(account), frappe.bold(project.project_name)
				)
				if account
				else _("Budget of project {0}").format(frappe.bold(project.project_name))
			)
			message = _("{0} is {1}. It will be exceeded by {2} (spent {3}).").format(
				scope,
				fmt_money(allocated, currency=currency),
				frappe.bold(fmt_money(total - allocated, currency=currency)),
				fmt_money(total, currency=currency),
			)
			if project.action_if_exceeded == "Stop" and doc.get("voucher_type") != "Depreciation Entry":
				frappe.throw(message, BudgetExceededError, title=_("Project Budget Exceeded"))
			frappe.msgprint(message, indicator="orange", title=_("Project Budget Exceeded"))
