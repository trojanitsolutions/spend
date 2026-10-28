import frappe
from frappe.utils import flt, fmt_money

from spend.spend.accounting import GL_PRECISION, get_allowed_accounts, get_company_currency, is_project_account


def execute():
	"""Bring existing projects in line with the rules on project budgets.

	A project that holds a revised Budget alone takes the revision as its share. Expense debits
	outside the budgeted accounts of their project, or of their cost center, stay posted and are
	listed: on the project, else in the Error Log.
	"""
	set_revised_shares()
	report_unbudgeted_expenses()


def set_revised_shares():
	from spend.projects.doctype.project.project import get_allocations, get_sole_project

	for name in frappe.get_all(
		"Budget", filters={"docstatus": 1, "amended_from": ("is", "set")}, pluck="name"
	):
		project = get_sole_project(get_allocations(name))
		if not project:
			continue
		budget = frappe.get_doc("Budget", name)
		if get_share(project.budget_amount, project.accounts) == get_share(
			budget.total_budget, {r.account: r.budget_amount for r in budget.accounts}
		):
			continue
		frappe.db.savepoint("project_share")
		try:
			budget.set_project_share(project.name)
		except Exception:
			frappe.db.rollback(save_point="project_share")
			frappe.log_error(f"Could not set the share of Project {project.name} from Budget {name}")
		else:
			print(f"Project {project.name}: share set from Budget {name}")


def get_share(total, accounts: dict) -> tuple:
	return flt(total, GL_PRECISION), sorted((a, flt(v, GL_PRECISION)) for a, v in accounts.items())


def report_unbudgeted_expenses():
	"""Expense debits outside the budgeted accounts of their project, else of their cost center."""
	from spend.accounts.doctype.journal_entry.journal_entry import ASSET_ENTRY_TYPES

	gle = frappe.qb.DocType("GL Entry")
	acc = frappe.qb.DocType("Account")
	rows = (
		frappe.qb.from_(gle)
		.join(acc)
		.on(acc.name == gle.account)
		.select(
			gle.company,
			gle.project,
			gle.cost_center,
			gle.fiscal_year,
			gle.posting_date,
			gle.voucher_type,
			gle.voucher_no,
			gle.account,
			gle.debit,
			gle.credit,
		)
		.where((gle.is_cancelled == 0) & (acc.root_type == "Expense") & gle.cost_center.isnotnull())
		.orderby(gle.posting_date)
		.run(as_dict=True)
	)
	asset_entries = set(
		frappe.get_all(
			"Journal Entry",
			filters={
				"name": ("in", {r.voucher_no for r in rows if r.voucher_type == "Journal Entry"} or [""]),
				"voucher_type": ("in", ASSET_ENTRY_TYPES),
			},
			pluck="name",
		)
	)

	allowed, amounts = {}, {}
	for row in rows:
		if row.voucher_no in asset_entries:
			continue
		scope = ("Project", row.project) if row.project else ("Cost Center", row.cost_center, row.fiscal_year)
		if scope not in allowed:
			allowed[scope] = get_allowed_accounts(row.company, row.project, row.cost_center, row.posting_date)
		if is_project_account(row.account, allowed[scope]):
			continue
		key = (scope, row.company, row.voucher_type, row.voucher_no, row.account)
		amounts[key] = flt(amounts.get(key, 0) + flt(row.debit) - flt(row.credit), GL_PRECISION)

	outside = {}
	for (scope, company, voucher_type, voucher_no, account), amount in amounts.items():
		if amount > 0:  # only debits spend; a reversal or a refund does not
			line = f"{voucher_type} {voucher_no}: {account}, {fmt_money(amount, currency=get_company_currency(company))}"
			outside.setdefault(scope, []).append(line)

	for scope, lines in outside.items():
		if scope[0] != "Project":
			continue
		frappe.get_doc("Project", scope[1]).add_comment(
			"Info",
			"Booked outside its budgeted accounts ({0}) before this was checked:<ul>{1}</ul>".format(
				", ".join(allowed[scope]) or "none", "".join(f"<li>{line}</li>" for line in lines)
			),
		)
		print(f"Project {scope[1]}: {len(lines)} expense(s) outside its budgeted accounts")

	sections, count = [], 0
	for scope, lines in outside.items():
		if scope[0] != "Cost Center":
			continue
		_doctype, cost_center, fiscal_year = scope
		budgeted = ", ".join(allowed[scope]) or "none"
		sections.append(f"Cost Center {cost_center}, {fiscal_year} (budgeted: {budgeted}):\n" + "\n".join(lines))
		count += len(lines)
	if sections:
		frappe.log_error("Expenses outside budgeted accounts", "\n\n".join(sections))
		print(f"{count} expense(s) without a project outside budgeted accounts; see Error Log")
