# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder.functions import Coalesce, Sum
from frappe.utils import flt, fmt_money, getdate, today

from spend.spend.accounting import GL_PRECISION, get_subtree, validate_ledger_account
from spend.spend.doctype.journal_entry.journal_entry import validate_cost_center


class Project(Document):
	def validate(self):
		self.project_name = (self.project_name or "").strip()
		if self.cost_center:
			validate_cost_center(self.cost_center, self.company)
		if self.start_date and self.end_date and getdate(self.end_date) < getdate(self.start_date):
			frappe.throw(_("End Date cannot be before the Start Date"))
		self.validate_budget()
		self.validate_expense_categories()
		self.validate_budget_share()
		self.validate_approved_budget()
		self.validate_tasks()

	def validate_tasks(self):
		"""A project is completed only when all its tasks are completed or cancelled."""
		from spend.spend.doctype.task.task import get_open_tasks

		if self.status != "Completed" or self.is_new() or self.get_db_value("status") == "Completed":
			return
		open_tasks = get_open_tasks(self.name)
		if open_tasks:
			lines = "".join(f"<li>{frappe.bold(t.subject)} ({_(t.status)})</li>" for t in open_tasks[:10])
			more = _("and {0} more").format(len(open_tasks) - 10) if len(open_tasks) > 10 else ""
			frappe.throw(
				_("Complete or cancel all tasks of Project {0} before marking it completed:").format(
					frappe.bold(self.project_name)
				)
				+ f"<ul>{lines}</ul>{more}",
				title=_("Open Tasks"),
			)

	def validate_budget(self):
		if flt(self.budget_amount) < 0:
			frappe.throw(_("Total Budget cannot be negative"))
		seen = set()
		for row in self.budget_accounts:
			validate_ledger_account(
				row.account, self.company, _("Row {0}: Account").format(row.idx), root_types=("Expense",)
			)
			if row.account in seen:
				frappe.throw(_("Row {0}: Account {1} is repeated").format(row.idx, frappe.bold(row.account)))
			seen.add(row.account)
			if flt(row.budget_amount) <= 0:
				frappe.throw(_("Row {0}: Budget amount must be greater than zero").format(row.idx))

		limits = flt(sum(flt(r.budget_amount) for r in self.budget_accounts), GL_PRECISION)
		if flt(self.budget_amount) > 0 and limits > flt(self.budget_amount):
			frappe.throw(
				_("Account limits ({0}) add up to more than the Total Budget ({1})").format(
					limits, flt(self.budget_amount, GL_PRECISION)
				)
			)

	def validate_expense_categories(self):
		"""Each category or sub category once; a sub category's budget is a part of its category's."""
		from spend.spend.expense_category import validate_category

		seen, whole, parts = set(), {}, {}
		for row in self.expense_categories:
			validate_category(row, None, self.company, None, _("Category row {0}").format(row.idx))
			if flt(row.budget_amount) < 0:
				frappe.throw(_("Category row {0}: Budget amount cannot be negative").format(row.idx))
			key = (row.expense_category, row.expense_sub_category or None)
			if key in seen:
				frappe.throw(
					_("Category row {0}: {1} is repeated").format(
						row.idx, frappe.bold(row.expense_sub_category or row.expense_category)
					)
				)
			seen.add(key)
			if row.expense_sub_category:
				parts[row.expense_category] = parts.get(row.expense_category, 0) + flt(row.budget_amount)
			else:
				whole[row.expense_category] = flt(row.budget_amount)

		for category, amount in parts.items():
			limit = whole.get(category)
			if limit and flt(amount, GL_PRECISION) > limit:
				frappe.throw(
					_("The sub categories of {0} have budgets of {1}, more than its {2}").format(
						frappe.bold(category),
						fmt_money(amount, currency=self.currency),
						fmt_money(limit, currency=self.currency),
					)
				)
		total = flt(sum(whole.values()) + sum(a for c, a in parts.items() if c not in whole), GL_PRECISION)
		if flt(self.budget_amount) > 0 and total > flt(self.budget_amount):
			frappe.throw(
				_("Category budgets ({0}) add up to more than the Total Budget ({1})").format(
					fmt_money(total, currency=self.currency),
					fmt_money(self.budget_amount, currency=self.currency),
				)
			)

	def validate_budget_share(self):
		"""The project's amounts are a share of its Budget, which other projects share as well."""
		if not self.budget:
			return
		budget = frappe.get_doc("Budget", self.budget)
		before = self.get_doc_before_save()
		if not before or before.budget != self.budget:
			if budget.docstatus != 1:
				frappe.throw(_("Budget {0} is not submitted").format(frappe.bold(self.budget)))
			if budget.company != self.company:
				frappe.throw(_("Budget {0} belongs to another company").format(frappe.bold(self.budget)))

		if not self.cost_center and not frappe.db.get_value("Cost Center", budget.cost_center, "is_group"):
			self.cost_center = budget.cost_center
		if self.cost_center and self.cost_center not in get_subtree("Cost Center", budget.cost_center):
			frappe.throw(
				_("Cost Center {0} is not under {1}, the cost center of Budget {2}").format(
					frappe.bold(self.cost_center), frappe.bold(budget.cost_center), self.budget
				)
			)

		budget_accounts = {r.account for r in budget.accounts}
		for row in self.budget_accounts:
			if row.account not in budget_accounts:
				frappe.throw(
					_("Row {0}: Account {1} is not on Budget {2}").format(
						row.idx, frappe.bold(row.account), self.budget
					)
				)

		if self.status == "Cancelled":
			return
		allocations = get_allocations(self.budget, exclude=self.name)
		if not has_share(self):
			# without a share its recurring payments take from the Budget
			for payment in get_project_allocations(self.name)["recurring"]:
				add_allocation(allocations, payment)
		add_allocation(allocations, self)
		shortfalls = get_shortfalls(budget, allocations)
		if shortfalls:
			frappe.throw(
				_("The share of Project {0} does not fit in Budget {1}:").format(
					frappe.bold(self.project_name), self.budget
				)
				+ "<br>"
				+ format_shortfalls(shortfalls, self.currency),
				title=_("Over the Budget"),
			)
		self.validate_recurring_payments()

	def validate_recurring_payments(self):
		"""The share must still hold the project's recurring payments."""
		if self.is_new() or not has_share(self):
			return
		shortfalls = get_project_shortfalls(self, get_project_allocations(self.name))
		if shortfalls:
			frappe.throw(
				_("The recurring payments of Project {0} take more than its share:").format(
					frappe.bold(self.project_name)
				)
				+ "<br>"
				+ "<br>".join(
					_("{0}: the share is {1}, recurring payments hold {2} ({3})").format(
						s.label,
						fmt_money(s.available, currency=self.currency),
						fmt_money(s.held, currency=self.currency),
						s.holders,
					)
					for s in shortfalls
				),
				title=_("Over the Share"),
			)

	def on_update(self):
		# recurring payments take their money from the project's Budget
		if self.has_value_changed("budget"):
			rp = frappe.qb.DocType("Recurring Payment")
			frappe.qb.update(rp).set(rp.budget, self.budget).where(rp.project == self.name).run()

	def validate_approved_budget(self):
		"""An approved budget changes only through Revise, which sends it for approval again."""
		from spend.spend.approval import APPROVED, is_approval_required

		before = self.get_doc_before_save()
		if not before or before.workflow_state != APPROVED or self.workflow_state != APPROVED:
			return
		if not is_approval_required(self.doctype):
			return
		if get_budget_key(before) != get_budget_key(self):
			frappe.throw(
				_("The budget of Project {0} is approved. Use Revise to change it.").format(
					frappe.bold(self.project_name)
				)
			)

	def on_trash(self):
		for doctype in ("Purchase Invoice", "Supplier Payment", "Recurring Payment", "GL Entry", "Task"):
			if frappe.db.exists(doctype, {"project": self.name}):
				frappe.throw(
					_(
						"Cannot delete Project {0} because {1} records exist. Set it to Cancelled instead."
					).format(frappe.bold(self.project_name), _(doctype))
				)


def get_budget_key(doc) -> tuple:
	return (
		doc.budget,
		flt(doc.budget_amount, GL_PRECISION),
		doc.action_if_exceeded,
		sorted((r.account, flt(r.budget_amount, GL_PRECISION)) for r in doc.budget_accounts),
		sorted(
			(r.expense_category, r.expense_sub_category or "", flt(r.budget_amount, GL_PRECISION))
			for r in doc.get("expense_categories") or []
		),
	)


def new_allocations() -> dict:
	return {"total": 0.0, "accounts": {}, "holders": [], "projects": [], "recurring": []}


def has_share(project) -> bool:
	"""A project with a total or account rows has a share, which its recurring payments take from."""
	return flt(project.budget_amount) > 0 or bool(project.budget_accounts)


def get_projects_with_share(names) -> set:
	"""The projects among `names` that have a share; the payments of the others take from the Budget."""
	names = list({n for n in names if n})
	if not names:
		return set()
	with_rows = frappe.get_all(
		"Project Budget Account",
		filters={"parenttype": "Project", "parent": ("in", names)},
		pluck="parent",
		distinct=True,
	)
	with_total = frappe.get_all(
		"Project", filters={"name": ("in", names), "budget_amount": (">", 0)}, pluck="name"
	)
	return {*with_rows, *with_total}


def get_allocations(budget: str, exclude: str | None = None) -> dict:
	"""What a Budget's projects, and its recurring payments outside a project's share, hold of it.

	`exclude` is a project or a recurring payment being checked; a project's own payments are left out too.
	"""
	projects = frappe.get_all(
		"Project",
		filters={"budget": budget, "status": ("!=", "Cancelled"), "name": ("!=", exclude or "")},
		fields=["name", "project_name", "budget_amount", "status"],
		order_by="creation",
	)
	allocations = new_allocations()
	rows = frappe.get_all(
		"Project Budget Account",
		filters={"parenttype": "Project", "parent": ("in", [p.name for p in projects] or [""])},
		fields=["parent", "account", "budget_amount"],
	)
	for project in projects:
		project.update(
			doctype="Project",
			title=project.project_name,
			accounts={r.account: flt(r.budget_amount) for r in rows if r.parent == project.name},
		)
		add_allocation(allocations, project)
	payments = get_recurring_holds({"budget": budget}, exclude)
	with_share = get_projects_with_share(p.project for p in payments)
	for payment in payments:
		if payment.project and (payment.project == exclude or payment.project in with_share):
			continue
		add_allocation(allocations, payment)
	return allocations


def get_project_allocations(project: str, exclude: str | None = None) -> dict:
	"""What the recurring payments of a project hold of its share."""
	allocations = new_allocations()
	for payment in get_recurring_holds({"project": project}, exclude):
		add_allocation(allocations, payment)
	return allocations


def get_recurring_holds(filters: dict, exclude: str | None = None) -> list:
	"""Recurring payments with what each holds.

	A submitted one holds its total. A cancelled one holds what it paid, as its
	payments stay on the books; its amendment holds the rest. A draft holds nothing.
	"""
	payments = frappe.get_all(
		"Recurring Payment",
		filters={**filters, "docstatus": ("!=", 0), "name": ("!=", exclude or "")},
		fields=[
			"name",
			"title",
			"project",
			"expense_account",
			"total_amount",
			"paid_amount",
			"status",
			"docstatus",
		],
		order_by="creation",
	)
	holds = []
	for payment in payments:
		held = flt(payment.total_amount if payment.docstatus == 1 else payment.paid_amount, GL_PRECISION)
		if held:
			holds.append(make_recurring_holder(payment, held))
	return holds


def make_recurring_holder(payment, held: float):
	return frappe._dict(
		doctype="Recurring Payment",
		name=payment.name,
		title=" ".join(filter(None, (payment.name, payment.title))),
		project=payment.project,
		account=payment.expense_account,
		budget_amount=held,
		paid=flt(payment.paid_amount, GL_PRECISION),
		remaining=flt(held - flt(payment.paid_amount), GL_PRECISION),
		status=payment.status,
		accounts={payment.expense_account: held},
	)


def add_allocation(allocations: dict, holder):
	if holder.get("doctype") == "Project" and not isinstance(holder.get("accounts"), dict):
		holder = frappe._dict(
			doctype="Project",
			name=holder.name,
			title=holder.project_name,
			project_name=holder.project_name,
			budget_amount=holder.budget_amount,
			status=holder.status,
			accounts={r.account: flt(r.budget_amount) for r in holder.budget_accounts},
		)
	allocations["holders"].append(holder)
	allocations["projects" if holder.doctype == "Project" else "recurring"].append(holder)
	allocations["total"] = flt(allocations["total"] + flt(holder.budget_amount), GL_PRECISION)
	for account, amount in holder.accounts.items():
		held = allocations["accounts"].get(account, 0.0)
		allocations["accounts"][account] = flt(held + amount, GL_PRECISION)


def get_shortfalls(budget, allocations: dict) -> list:
	"""Each account (and the total) where the holders take more than `budget` has."""
	amounts = {r.account: flt(r.budget_amount, GL_PRECISION) for r in budget.accounts}
	return find_shortfalls(amounts, flt(budget.total_budget, GL_PRECISION), allocations)


def get_project_shortfalls(project, allocations: dict) -> list:
	"""Each account (and the total) where recurring payments take more than the project's share.

	A project without account rows has only its total share.
	"""
	shares = {r.account: flt(r.budget_amount, GL_PRECISION) for r in project.budget_accounts}
	total = flt(project.budget_amount, GL_PRECISION)
	return find_shortfalls(shares, total if total or not shares else None, allocations, accounts=bool(shares))


def find_shortfalls(amounts: dict, total: float | None, allocations: dict, accounts: bool = True) -> list:
	"""`own` is the part held by the last holder added, the one being checked."""
	holders = allocations["holders"]
	last = holders[-1] if holders else None
	checks = []
	if accounts:
		checks = [
			(account, held, amounts.get(account, 0.0), lambda h, a=account: a in h.accounts)
			for account, held in allocations["accounts"].items()
		]
	if total is not None:
		checks.append((_("Total"), allocations["total"], total, None))

	shortfalls = []
	for label, held, available, holds in checks:
		if held <= available:
			continue
		takers = [h for h in holders if (holds(h) if holds else flt(h.budget_amount) > 0)]
		own = 0.0
		if last:
			own = flt(last.budget_amount) if holds is None else flt(last.accounts.get(label))
		shortfalls.append(
			frappe._dict(
				label=label,
				held=held,
				available=available,
				own=own,
				holders=", ".join(h.title for h in takers),
				others=", ".join(h.title for h in takers if h is not last),
			)
		)
	return shortfalls


def format_shortfalls(shortfalls: list, currency: str | None) -> str:
	return "<br>".join(
		_("{0}: {1} is free, others hold {2} ({3})").format(
			s.label,
			fmt_money(max(s.available - s.held + s.own, 0), currency=currency),
			fmt_money(s.held - s.own, currency=currency),
			s.others or _("none"),
		)
		for s in shortfalls
	)


@frappe.whitelist()
def get_budget_allocation(budget: str, project: str | None = None) -> dict:
	"""A Budget's accounts with what its projects and recurring payments hold and what is still free."""
	doc = frappe.get_doc("Budget", budget)
	doc.check_permission("read")
	allocations = get_allocations(budget, exclude=project)
	spent = get_spend_by_project(projects=[p.name for p in allocations["projects"]])
	# every recurring payment on the budget; those of a project with a share take from it, not again from the budget
	recurring = get_recurring_holds({"budget": budget})
	with_share = get_projects_with_share(r.project for r in recurring)
	project_names = dict(
		frappe.get_all(
			"Project",
			filters={"name": ("in", {r.project for r in recurring if r.project} or [""])},
			fields=["name", "project_name"],
			as_list=True,
		)
	)
	return {
		"name": doc.name,
		"company": doc.company,
		"cost_center": doc.cost_center,
		**frappe.db.get_value(
			"Cost Center", doc.cost_center, ["is_group as cost_center_is_group", "lft", "rgt"], as_dict=True
		),
		"action_if_exceeded": doc.action_if_exceeded,
		"currency": doc.currency,
		"total": flt(doc.total_budget, GL_PRECISION),
		"held": allocations["total"],
		"free": flt(doc.total_budget - allocations["total"], GL_PRECISION),
		"accounts": [
			{
				"account": r.account,
				"budget": flt(r.budget_amount, GL_PRECISION),
				"held": allocations["accounts"].get(r.account, 0.0),
				"free": flt(r.budget_amount - allocations["accounts"].get(r.account, 0.0), GL_PRECISION),
			}
			for r in doc.accounts
		],
		"projects": [
			{**p, "spent": spent.get(p.name, 0.0), "route": f"/spend/projects/{p.name}"}
			for p in allocations["projects"]
		],
		"recurring": [
			{
				**r,
				"project_name": project_names.get(r.project),
				"counted": r.project not in with_share,
				"route": f"/spend/recurring/{r.name}",
			}
			for r in recurring
		],
		"recurring_held": flt(sum(r.budget_amount for r in recurring), GL_PRECISION),
		"recurring_paid": flt(sum(r.paid for r in recurring), GL_PRECISION),
		"recurring_remaining": flt(sum(r.remaining for r in recurring), GL_PRECISION),
	}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_budget_accounts(doctype, txt, searchfield, start, page_len, filters):
	"""Account search in Desk, limited to the accounts of the project's Budget."""
	budget = filters.get("budget")
	if not budget:
		return []
	frappe.get_doc("Budget", budget).check_permission("read")
	return frappe.get_all(
		"Budget Account",
		filters={"parenttype": "Budget", "parent": budget, "account": ("like", f"%{txt}%")},
		fields=["account"],
		start=start,
		page_length=page_len,
		as_list=True,
	)


def get_spend_by_project(
	company: str | None = None, projects: list | None = None, account: str | None = None
) -> dict:
	"""Net expense booked to each project, read from the ledger in one grouped query."""
	gle = frappe.qb.DocType("GL Entry")
	acc = frappe.qb.DocType("Account")
	query = (
		frappe.qb.from_(gle)
		.join(acc)
		.on(acc.name == gle.account)
		.select(gle.project, Coalesce(Sum(gle.debit), 0) - Coalesce(Sum(gle.credit), 0))
		.where((gle.is_cancelled == 0) & (acc.root_type == "Expense") & gle.project.isnotnull())
		.groupby(gle.project)
	)
	if company:
		query = query.where(gle.company == company)
	if projects is not None:
		if not projects:
			return {}
		query = query.where(gle.project.isin(projects))
	if account:
		query = query.where(gle.account.isin(get_subtree("Account", account)))
	return {project: flt(amount, GL_PRECISION) for project, amount in query.run()}


def get_project_spent(project: str, account: str | None = None) -> float:
	return get_spend_by_project(projects=[project], account=account).get(project, 0.0)


def get_bill_totals(projects: list) -> dict:
	"""Billed and outstanding on the submitted bills of each project."""
	if not projects:
		return {}
	pi = frappe.qb.DocType("Purchase Invoice")
	rows = (
		frappe.qb.from_(pi)
		.select(pi.project, Sum(pi.grand_total), Sum(pi.outstanding_amount))
		.where((pi.docstatus == 1) & pi.project.isin(projects))
		.groupby(pi.project)
		.run()
	)
	totals = {}
	for project, billed, outstanding in rows:
		billed, outstanding = flt(billed, GL_PRECISION), flt(outstanding, GL_PRECISION)
		totals[project] = {
			"billed": billed,
			"outstanding": outstanding,
			"paid": flt(billed - outstanding, GL_PRECISION),
		}
	return totals


def make_project_row(project, spent: float, bills: dict | None) -> dict:
	budget = flt(project.budget_amount, GL_PRECISION)
	bills = bills or {"billed": 0.0, "paid": 0.0, "outstanding": 0.0}
	return {
		**project,
		"spent": spent,
		"remaining": flt(budget - spent, GL_PRECISION) if budget else None,
		"utilization": flt(spent / budget * 100, 2) if budget else None,
		**bills,
	}


@frappe.whitelist()
def get_project_summary(project: str) -> dict:
	from spend.spend.doctype.recurring_payment.recurring_payment import get_recurring_rows

	doc = frappe.get_doc("Project", project)
	doc.check_permission("read")
	spent = get_project_spent(doc.name)
	summary = make_project_row(
		frappe._dict(budget_amount=doc.budget_amount), spent, get_bill_totals([doc.name]).get(doc.name)
	)
	summary.pop("budget_amount")

	accounts = []
	for row in doc.budget_accounts:
		actual = get_project_spent(doc.name, row.account)
		budget = flt(row.budget_amount, GL_PRECISION)
		accounts.append(
			{
				"account": row.account,
				"account_number": frappe.db.get_value("Account", row.account, "account_number"),
				"budget": budget,
				"actual": actual,
				"remaining": flt(budget - actual, GL_PRECISION),
				"utilization": flt(actual / budget * 100, 2) if budget else 0,
			}
		)

	return {
		"doc": doc.as_dict(),
		**summary,
		"accounts": accounts,
		**get_category_summary(doc),
		"bills": frappe.get_list(
			"Purchase Invoice",
			filters={"project": doc.name},
			fields=[
				"name",
				"supplier",
				"bill_no",
				"posting_date",
				"due_date",
				"grand_total",
				"outstanding_amount",
				"status",
			],
			order_by="posting_date desc, creation desc",
			limit=100,
		),
		"payments": frappe.get_list(
			"Supplier Payment",
			filters={"project": doc.name, "docstatus": (">", 0)},
			fields=[
				"name",
				"supplier",
				"posting_date",
				"mode_of_payment",
				"reference_no",
				"paid_amount",
				"docstatus",
			],
			order_by="posting_date desc, creation desc",
			limit=100,
		),
		"recurring": get_recurring_rows({"project": doc.name}, limit=100)
		if frappe.has_permission("Recurring Payment", "read")
		else [],
		**get_task_summary(doc.name),
		"can_write": doc.has_permission("write"),
	}


def get_task_summary(project: str) -> dict:
	from spend.spend.doctype.task.task import DONE

	if not frappe.has_permission("Task", "read"):
		return {"tasks": [], "open_tasks": 0}
	tasks = frappe.get_list(
		"Task",
		filters={"project": project},
		fields=[
			"name",
			"subject",
			"status",
			"priority",
			"exp_start_date",
			"exp_end_date",
			"progress",
			"parent_task",
			"is_group",
			"is_milestone",
			"_assign",
		],
		order_by="lft",
	)
	return {"tasks": tasks, "open_tasks": sum(1 for t in tasks if t.status not in DONE)}


def get_category_summary(project) -> dict:
	"""Budget and charge of each category of the project, and its charge in each month."""
	from spend.spend.expense_category import (
		build_monthly,
		get_category_monthly,
		get_category_spent,
		get_project_months,
	)

	categories = []
	for row in project.expense_categories:
		budget = flt(row.budget_amount, GL_PRECISION)
		charged = get_category_spent(project.name, row.expense_category, row.expense_sub_category)
		categories.append(
			{
				"category": row.expense_category,
				"sub_category": row.expense_sub_category,
				"budget": budget,
				"charged": charged,
				"remaining": flt(budget - charged, GL_PRECISION) if budget else None,
				"utilization": flt(charged / budget * 100, 2) if budget else None,
			}
		)

	months = get_project_months(project)
	entries = get_category_monthly(f"{months[0]}-01", today(), project=project.name)
	pairs = [(r.expense_category, r.expense_sub_category) for r in project.expense_categories]
	return {
		"categories": categories,
		"monthly": {"months": months, "rows": build_monthly(entries, months, pairs)},
	}
