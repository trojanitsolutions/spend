# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

"""Expense categories tag project spend: a parent category and, optionally, one of its sub categories."""

import frappe
from frappe import _
from frappe.query_builder.functions import Coalesce, Extract, Sum
from frappe.utils import add_months, flt, fmt_money, get_first_day, getdate, today

from spend.spend.accounting import GL_PRECISION


def get_project_category_rows(project: str) -> list:
	return frappe.get_all(
		"Project Expense Category",
		filters={"parent": project, "parenttype": "Project", "parentfield": "expense_categories"},
		fields=["expense_category", "expense_sub_category", "budget_amount"],
		order_by="idx",
	)


def covers(row, category: str, sub_category: str | None) -> bool:
	"""A project row without a sub category covers the whole category."""
	return row.expense_category == category and (
		not row.expense_sub_category or row.expense_sub_category == sub_category
	)


def validate_category(row, project: str | None, company: str, account: str | None, label: str):
	"""Check the category and sub category of a booking line, filling the category from the sub category."""
	if not row.expense_category and not row.expense_sub_category:
		return
	if row.expense_sub_category and not row.expense_category:
		row.expense_category = frappe.db.get_value(
			"Expense Category", row.expense_sub_category, "parent_category"
		)

	category = get_category(row.expense_category, company, label)
	if not category.is_parent_category:
		frappe.throw(
			_("{0}: {1} is a sub category. Pick it as the Sub Category.").format(
				label, frappe.bold(row.expense_category)
			)
		)
	if row.expense_sub_category:
		sub_category = get_category(row.expense_sub_category, company, label)
		if sub_category.parent_category != row.expense_category:
			frappe.throw(
				_("{0}: {1} is not a sub category of {2}").format(
					label, frappe.bold(row.expense_sub_category), frappe.bold(row.expense_category)
				)
			)
	if account and frappe.db.get_value("Account", account, "root_type") != "Expense":
		frappe.throw(_("{0}: an expense category needs an Expense account").format(label))

	rows = get_project_category_rows(project) if project else []
	if rows and not any(covers(r, row.expense_category, row.expense_sub_category) for r in rows):
		name = frappe.bold(row.expense_sub_category or row.expense_category)
		frappe.throw(
			_("{0}: {1} is not one of the expense categories of Project {2}").format(
				label, name, frappe.bold(project)
			)
		)


def get_category(name: str, company: str, label: str):
	category = frappe.db.get_value(
		"Expense Category",
		name,
		["company", "disabled", "is_parent_category", "parent_category"],
		as_dict=True,
	)
	if not category:
		frappe.throw(_("{0}: Expense Category {1} does not exist").format(label, name))
	if category.company != company:
		frappe.throw(
			_("{0}: Expense Category {1} does not belong to Company {2}").format(
				label, frappe.bold(name), frappe.bold(company)
			)
		)
	if category.disabled:
		frappe.throw(_("{0}: Expense Category {1} is disabled").format(label, frappe.bold(name)))
	return category


@frappe.whitelist()
def get_category_account(category: str | None = None, sub_category: str | None = None) -> str | None:
	"""The expense account of the sub category, else of its parent category."""
	for name in filter(None, (sub_category, category)):
		frappe.has_permission("Expense Category", "read", name, throw=True)
		account, parent = frappe.db.get_value(
			"Expense Category", name, ["expense_account", "parent_category"]
		)
		if account:
			return account
		if parent:
			return frappe.db.get_value("Expense Category", parent, "expense_account")
	return None


def get_category_spent(project: str, category: str, sub_category: str | None = None) -> float:
	gle = frappe.qb.DocType("GL Entry")
	acc = frappe.qb.DocType("Account")
	query = (
		frappe.qb.from_(gle)
		.join(acc)
		.on(acc.name == gle.account)
		.select(Coalesce(Sum(gle.debit), 0) - Coalesce(Sum(gle.credit), 0))
		.where(
			(gle.is_cancelled == 0)
			& (acc.root_type == "Expense")
			& (gle.project == project)
			& (gle.expense_category == category)
		)
	)
	if sub_category:
		query = query.where(gle.expense_sub_category == sub_category)
	return flt(query.run()[0][0], GL_PRECISION)


def get_category_label(row) -> str:
	return " / ".join(filter(None, (row.expense_category, row.expense_sub_category)))


def validate_category_budget(doc, lines: list[tuple]):
	"""Check the expense lines of a voucher against the category budgets of their projects.

	`lines` are (account, project, category, sub category, amount) tuples.
	"""
	from spend.budgeting.doctype.budget.budget import BudgetExceededError

	pending = {}
	for account, project, category, sub_category, amount in lines:
		if not (project and category) or frappe.db.get_value("Account", account, "root_type") != "Expense":
			continue
		pending.setdefault(project, []).append((category, sub_category, flt(amount)))

	for project_name, amounts in pending.items():
		project = frappe.db.get_value(
			"Project", project_name, ["project_name", "action_if_exceeded", "currency"], as_dict=True
		)
		if project.action_if_exceeded == "Ignore":
			continue
		currency = project.currency or doc.get("currency")
		for row in get_project_category_rows(project_name):
			if flt(row.budget_amount) <= 0:
				continue
			amount = sum(a for category, sub, a in amounts if covers(row, category, sub))
			if amount <= 0:
				continue
			total = flt(
				get_category_spent(project_name, row.expense_category, row.expense_sub_category) + amount,
				GL_PRECISION,
			)
			if total <= flt(row.budget_amount):
				continue
			message = _(
				"Budget for category {0} on project {1} is {2}. It will be exceeded by {3} (spent {4})."
			).format(
				frappe.bold(get_category_label(row)),
				frappe.bold(project.project_name),
				fmt_money(row.budget_amount, currency=currency),
				frappe.bold(fmt_money(total - flt(row.budget_amount), currency=currency)),
				fmt_money(total, currency=currency),
			)
			if project.action_if_exceeded == "Stop" and doc.get("voucher_type") != "Depreciation Entry":
				frappe.throw(message, BudgetExceededError, title=_("Category Budget Exceeded"))
			frappe.msgprint(message, indicator="orange", title=_("Category Budget Exceeded"))


def get_category_room(project: str, category: str, sub_category: str | None, exclude: str | None = None):
	"""What a recurring payment can still take from each category budget it falls under.

	Returns (row, free) pairs: the budget less what is spent and what other recurring
	payments still hold. What they paid is already spent.
	"""
	from spend.projects.doctype.project.project import get_recurring_holds

	rooms = []
	for row in get_project_category_rows(project):
		if flt(row.budget_amount) <= 0 or not covers(row, category, sub_category):
			continue
		filters = {"project": project, "expense_category": row.expense_category}
		if row.expense_sub_category:
			filters["expense_sub_category"] = row.expense_sub_category
		holding = sum(h.remaining for h in get_recurring_holds(filters, exclude))
		spent = get_category_spent(project, row.expense_category, row.expense_sub_category)
		rooms.append((row, flt(flt(row.budget_amount) - spent - holding, GL_PRECISION)))
	return rooms


def get_category_monthly(
	from_date, to_date, company: str | None = None, project: str | None = None, category: str | None = None
) -> list:
	"""Net expense of each category and sub category in each month, read from the ledger."""
	gle = frappe.qb.DocType("GL Entry")
	acc = frappe.qb.DocType("Account")
	year, month = Extract("year", gle.posting_date), Extract("month", gle.posting_date)
	query = (
		frappe.qb.from_(gle)
		.join(acc)
		.on(acc.name == gle.account)
		.select(
			gle.expense_category,
			gle.expense_sub_category,
			year,
			month,
			Coalesce(Sum(gle.debit), 0) - Coalesce(Sum(gle.credit), 0),
		)
		.where(
			(gle.is_cancelled == 0)
			& (acc.root_type == "Expense")
			& gle.expense_category.isnotnull()
			& (gle.posting_date >= from_date)
			& (gle.posting_date <= to_date)
		)
		.groupby(gle.expense_category, gle.expense_sub_category, year, month)
	)
	if company:
		query = query.where(gle.company == company)
	if project:
		query = query.where(gle.project == project)
	if category:
		query = query.where(gle.expense_category == category)
	return [
		frappe._dict(
			category=cat, sub_category=sub, month=f"{int(y)}-{int(m):02d}", amount=flt(amount, GL_PRECISION)
		)
		for cat, sub, y, m, amount in query.run()
	]


def get_months(from_date, to_date) -> list[str]:
	months, current, end = [], get_first_day(from_date), getdate(to_date)
	while current <= end:
		months.append(current.strftime("%Y-%m"))
		current = add_months(current, 1)
	return months


def build_monthly(entries: list, months: list[str], categories: list | None = None) -> list[dict]:
	"""Rows for each category, each followed by its sub categories, with the amount of each month.

	`categories` are (category, sub category) pairs that get a row even with nothing charged.
	"""
	parents, subs = {}, {}

	def get_row(category, sub_category):
		rows = subs.setdefault(category, {}) if sub_category else parents
		key = sub_category or category
		if key not in rows:
			rows[key] = {
				"category": category,
				"sub_category": sub_category,
				"indent": 1 if sub_category else 0,
				"months": dict.fromkeys(months, 0.0),
				"total": 0.0,
			}
		return rows[key]

	for category, sub_category in categories or []:
		get_row(category, None)
		if sub_category:
			get_row(category, sub_category)
	for entry in entries:
		if entry.month not in months:
			continue
		targets = [get_row(entry.category, None)]
		if entry.sub_category:
			targets.append(get_row(entry.category, entry.sub_category))
		for row in targets:
			row["months"][entry.month] = flt(row["months"][entry.month] + entry.amount, GL_PRECISION)
			row["total"] = flt(row["total"] + entry.amount, GL_PRECISION)

	rows = []
	for category in sorted(parents):
		rows.append(parents[category])
		rows.extend(subs.get(category, {})[sub] for sub in sorted(subs.get(category, {})))
	return rows


def get_project_months(project) -> list[str]:
	"""The months of the project up to today, at most the last 24."""
	end = min(getdate(project.end_date or today()), getdate(today()))
	start = getdate(project.start_date) if project.start_date else add_months(end, -11)
	start = max(start, add_months(end, -23))
	return get_months(min(start, end), end)
