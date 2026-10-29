# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

"""Endpoints for the Spend web app (frontend/). Reports are run through
`frappe.desk.query_report.run`; documents through the standard client APIs."""

import frappe
from frappe import _
from frappe.query_builder.functions import Coalesce, Count, Sum
from frappe.utils import add_months, flt, get_first_day, get_last_day, getdate, nowdate
from frappe.utils.modules import get_blocked_modules

from spend.spend.accounting import GL_PRECISION, get_fiscal_year
from spend.spend.approval import get_active_approvals
from spend.spend.doctype.frontend_template.frontend_template import get_active_template
from spend.projects.doctype.project.project import get_bill_totals, get_spend_by_project, make_project_row
from spend.purchasing.doctype.recurring_payment.recurring_payment import get_recurring_rows, get_upcoming_payments
from spend.spend.setup import ROLES
from spend.training.access import is_trainer

APP_ROLES = {*ROLES, "System Manager"}


def has_app_permission() -> bool:
	return frappe.session.user == "Administrator" or bool(APP_ROLES & set(frappe.get_roles()))


def check_app_permission():
	if not has_app_permission():
		frappe.throw(_("You do not have access to Spend"), frappe.PermissionError)


@frappe.whitelist()
def get_boot() -> dict:
	check_app_permission()
	companies = get_reference_list(
		"Company", fields=["name", "abbr", "default_currency", "is_training"], order_by="company_name"
	)
	fiscal_years = get_reference_list(
		"Fiscal Year",
		filters={"disabled": 0},
		fields=["name", "start_date", "end_date"],
		order_by="start_date desc",
	)
	demo_companies = set(frappe.get_all("Demo Data Record", pluck="company", distinct=True))
	for company in companies:
		company["has_demo_data"] = company["name"] in demo_companies
	user_company = frappe.defaults.get_user_default("Company")
	blocked = set(get_blocked_modules())
	return {
		"user": frappe.session.user,
		"full_name": frappe.utils.get_fullname(frappe.session.user),
		"companies": companies,
		"default_company": user_company if user_company in {c.name for c in companies} else None,
		"fiscal_years": fiscal_years,
		"current_fiscal_year": get_fiscal_year(nowdate(), throw=False),
		"approvals": get_active_approvals(),
		"roles": sorted(APP_ROLES & set(frappe.get_roles())),
		"permissions": {
			doctype: {
				"read": can_read(doctype, blocked),
				"create": frappe.has_permission(doctype, "create"),
				"submit": frappe.has_permission(doctype, "submit"),
				"write": frappe.has_permission(doctype, "write"),
				"delete": frappe.has_permission(doctype, "delete"),
				"cancel": frappe.has_permission(doctype, "cancel"),
			}
			for doctype in (
				"Asset",
				"Budget",
				"Journal Entry",
				"Company",
				"Account",
				"Cost Center",
				"GL Entry",
				"Fiscal Year",
				"Supplier",
				"Purchase Invoice",
				"Supplier Payment",
				"Project",
				"Expense Category",
				"Task",
				"Recurring Payment",
				"Spend Settings",
				"Item",
				"Item Group",
				"UOM",
				"Frontend Template",
			)
		},
		"reports": get_allowed_reports(blocked),
		"can_setup": bool(frappe.has_permission("Company", "create")),
		"is_trainer": is_trainer(),
		"theme": get_active_template(),
		"default_currency": frappe.db.get_single_value("System Settings", "currency") or "INR",
	}


def can_read(doctype: str, blocked: set[str] | None = None) -> bool:
	"""Read permission on the doctype, and its module not blocked for the user."""
	if blocked is None:
		blocked = set(get_blocked_modules())
	return frappe.has_permission(doctype, "read") and frappe.get_meta(doctype).module not in blocked


def get_reference_list(doctype: str, **kwargs) -> list:
	"""Companies and fiscal years the app shell needs. A role that cannot read the doctype, such as
	General Manager, still gets the plain list, since every page is scoped by company."""
	return frappe.get_list(doctype, ignore_permissions=not frappe.has_permission(doctype, "read"), **kwargs)


def get_allowed_reports(blocked: set[str]) -> list[str]:
	"""Spend reports this user may run: enabled, permitted to one of their roles, and not in a
	module blocked for them."""
	reports = frappe.get_all(
		"Report",
		filters={"module": ("in", frappe.get_module_list("spend")), "disabled": 0},
		fields=["name", "module"],
	)
	return sorted(
		r.name for r in reports if r.module not in blocked and frappe.get_cached_doc("Report", r.name).is_permitted()
	)


@frappe.whitelist()
def get_dashboard(company: str) -> dict:
	check_app_permission()
	if frappe.has_permission("Company", "read"):
		frappe.has_permission("Company", "read", company, throw=True)
	elif not frappe.db.exists("Company", company):
		frappe.throw(_("Company {0} does not exist").format(company), frappe.DoesNotExistError)
	today = getdate(nowdate())
	fiscal_year = get_fiscal_year(today, throw=False)
	currency = frappe.get_cached_value("Company", company, "default_currency")
	blocked = set(get_blocked_modules())

	def allowed(doctype):
		return can_read(doctype, blocked)

	# a section is None when the user cannot read what it is built from
	return {
		"currency": currency,
		"fiscal_year": fiscal_year,
		"assets": get_asset_kpis(company) if allowed("Asset") else None,
		"depreciation_due": get_depreciation_due(company, today) if allowed("Asset") else None,
		"budget": get_budget_kpis(company, fiscal_year) if allowed("Budget") else None,
		"spending_trend": get_spending_trend(company, today) if allowed("GL Entry") else None,
		"top_cost_centers": get_top_cost_centers(company, fiscal_year) if allowed("Cost Center") else None,
		"payables": get_payables(company, today) if allowed("Purchase Invoice") else None,
		"projects": get_project_kpis(company) if allowed("Project") else None,
		"upcoming_payments": get_upcoming_payments(company) if allowed("Recurring Payment") else [],
		"recent_entries": frappe.get_list(
			"Journal Entry",
			filters={"company": company, "docstatus": 1},
			fields=["name", "title", "voucher_type", "posting_date", "total_debit"],
			order_by="posting_date desc, creation desc",
			limit=6,
		)
		if allowed("Journal Entry")
		else None,
	}


def get_asset_kpis(company):
	rows = frappe.get_list(
		"Asset",
		filters={"company": company, "docstatus": 1},
		fields=["status", "gross_purchase_amount", "accumulated_depreciation", "value_after_depreciation"],
		limit=0,
	)
	by_status = {}
	for r in rows:
		by_status[r.status] = by_status.get(r.status, 0) + 1
	return {
		"by_status": by_status,
		"count": len(rows),
		"gross": flt(sum(flt(r.gross_purchase_amount) for r in rows), GL_PRECISION),
		"accumulated": flt(sum(flt(r.accumulated_depreciation) for r in rows), GL_PRECISION),
		"book_value": flt(sum(flt(r.value_after_depreciation) for r in rows), GL_PRECISION),
	}


def get_depreciation_due(company, today):
	ads = frappe.qb.DocType("Asset Depreciation Schedule")
	row = frappe.qb.DocType("Depreciation Schedule")
	count, amount = (
		frappe.qb.from_(ads)
		.join(row)
		.on(row.parent == ads.name)
		.select(Count(row.name), Coalesce(Sum(row.depreciation_amount), 0))
		.where(
			(ads.docstatus == 1)
			& (ads.company == company)
			& (row.schedule_date <= today)
			& (row.journal_entry.isnull() | (row.journal_entry == ""))
		)
		.run()[0]
	)
	return {"count": count, "amount": flt(amount, GL_PRECISION)}


def get_budget_kpis(company, fiscal_year):
	if not fiscal_year:
		return {"allocated": 0, "actual": 0, "utilization": 0, "budgets": []}
	from spend.budgeting.report.budget_utilization.budget_utilization import get_data

	budgets = get_data(frappe._dict(company=company, fiscal_year=fiscal_year))
	allocated = sum(b["allocated"] for b in budgets)
	actual = sum(b["actual"] for b in budgets)
	return {
		"allocated": flt(allocated, GL_PRECISION),
		"actual": flt(actual, GL_PRECISION),
		"utilization": flt(actual / allocated * 100, 1) if allocated else 0,
		"budgets": sorted(budgets, key=lambda b: -b["utilization"])[:5],
	}


def get_spending_trend(company, today):
	"""Expense posted per month over the last 12 months."""
	start = get_first_day(add_months(today, -11))
	gle = frappe.qb.DocType("GL Entry")
	account = frappe.qb.DocType("Account")
	rows = (
		frappe.qb.from_(gle)
		.join(account)
		.on(account.name == gle.account)
		.select(gle.posting_date, (gle.debit - gle.credit).as_("amount"))
		.where(
			(gle.is_cancelled == 0)
			& (gle.company == company)
			& (account.root_type == "Expense")
			& (gle.posting_date >= start)
			& (gle.posting_date <= get_last_day(today))
		)
		.run(as_dict=True)
	)
	months = {}
	for i in range(12):
		month = add_months(start, i)
		months[month.strftime("%Y-%m")] = {"month": month.strftime("%b %y"), "amount": 0.0}
	for r in rows:
		key = getdate(r.posting_date).strftime("%Y-%m")
		if key in months:
			months[key]["amount"] = flt(months[key]["amount"] + flt(r.amount), GL_PRECISION)
	return list(months.values())


def get_top_cost_centers(company, fiscal_year):
	if not fiscal_year:
		return []
	from spend.accounts.report.cost_center_wise_spending.cost_center_wise_spending import get_data

	start, end = frappe.db.get_value("Fiscal Year", fiscal_year, ["start_date", "end_date"])
	leaves = [r for r in get_data(company, start, end) if not r["is_group"] and r["spending"]]
	return [
		{"cost_center": r["name"], "spending": r["spending"], "budget": r["budget"]}
		for r in sorted(leaves, key=lambda r: -r["spending"])[:5]
	]


def get_payables(company, today):
	"""Amounts owed to suppliers on submitted bills."""
	bills = frappe.get_list(
		"Purchase Invoice",
		filters={"company": company, "docstatus": 1, "outstanding_amount": (">", 0)},
		fields=["supplier", "due_date", "outstanding_amount"],
		limit=0,
	)
	by_supplier, overdue, overdue_count = {}, 0.0, 0
	for bill in bills:
		by_supplier[bill.supplier] = flt(
			by_supplier.get(bill.supplier, 0) + bill.outstanding_amount, GL_PRECISION
		)
		if getdate(bill.due_date) < today:
			overdue += flt(bill.outstanding_amount)
			overdue_count += 1
	return {
		"outstanding": flt(sum(by_supplier.values()), GL_PRECISION),
		"overdue": flt(overdue, GL_PRECISION),
		"overdue_count": overdue_count,
		"open_bills": len(bills),
		"top_suppliers": [
			{"supplier": supplier, "outstanding": amount}
			for supplier, amount in sorted(by_supplier.items(), key=lambda item: -item[1])[:5]
		],
	}


def get_project_kpis(company):
	"""Open projects with their spend against budget, most used first."""
	projects = get_project_rows(company, "Open")
	budgeted = [p for p in projects if p["utilization"] is not None]
	return {
		"open": len(projects),
		"budget": flt(sum(flt(p["budget_amount"]) for p in budgeted), GL_PRECISION),
		"spent": flt(sum(p["spent"] for p in projects), GL_PRECISION),
		"over_budget": sum(1 for p in budgeted if p["remaining"] < 0),
		"top": sorted(budgeted, key=lambda p: -p["utilization"])[:5],
	}


def get_project_rows(company, status=None):
	filters = {"company": company}
	if status:
		filters["status"] = status
	projects = frappe.get_list(
		"Project",
		filters=filters,
		fields=["name", "project_name", "status", "start_date", "end_date", "budget_amount", "cost_center"],
		order_by="creation desc",
		limit=500,
	)
	names = [p.name for p in projects]
	spend = get_spend_by_project(company, names)
	bills = get_bill_totals(names)
	return [make_project_row(p, spend.get(p.name, 0.0), bills.get(p.name)) for p in projects]


@frappe.whitelist()
def get_projects(company: str, status: str | None = None) -> list[dict]:
	"""Projects with budget, spend and what is still owed on their bills."""
	check_app_permission()
	frappe.has_permission("Company", "read", company, throw=True)
	return get_project_rows(company, status)


@frappe.whitelist()
def get_recurring_payments(company: str, status: str | None = None) -> list[dict]:
	"""Recurring payments with their next date and what is left to pay."""
	check_app_permission()
	frappe.has_permission("Company", "read", company, throw=True)
	filters = {"company": company}
	if status:
		filters["status"] = status
	return get_recurring_rows(filters)


@frappe.whitelist()
def get_recurring_payment_detail(name: str) -> dict:
	check_app_permission()
	doc = frappe.get_doc("Recurring Payment", name)
	doc.check_permission("read")
	return {
		"doc": doc.as_dict(),
		"account_numbers": {
			a.name: a.account_number
			for a in frappe.get_all(
				"Account",
				filters={"name": ("in", [doc.expense_account, doc.paid_from])},
				fields=["name", "account_number"],
			)
		},
		"project_name": doc.project and frappe.db.get_value("Project", doc.project, "project_name"),
		"can_submit": doc.has_permission("submit"),
		"can_cancel": doc.has_permission("cancel"),
	}


@frappe.whitelist()
def get_suppliers(company: str, search: str | None = None) -> list[dict]:
	"""Suppliers with what the company owes each of them."""
	check_app_permission()
	frappe.has_permission("Company", "read", company, throw=True)
	filters = {"supplier_name": ("like", f"%{search}%")} if search else {}
	suppliers = frappe.get_list(
		"Supplier",
		filters=filters,
		fields=["name", "supplier_name", "tax_id", "email", "phone", "disabled"],
		order_by="supplier_name",
		limit=500,
	)
	owed = {}
	for bill in frappe.get_list(
		"Purchase Invoice",
		filters={"company": company, "docstatus": 1, "outstanding_amount": (">", 0)},
		fields=["supplier", "outstanding_amount", "due_date"],
		limit=0,
	):
		row = owed.setdefault(bill.supplier, {"outstanding": 0.0, "overdue": 0.0, "open_bills": 0})
		row["outstanding"] = flt(row["outstanding"] + bill.outstanding_amount, GL_PRECISION)
		row["open_bills"] += 1
		if getdate(bill.due_date) < getdate(nowdate()):
			row["overdue"] = flt(row["overdue"] + bill.outstanding_amount, GL_PRECISION)
	for supplier in suppliers:
		supplier.update(owed.get(supplier.name) or {"outstanding": 0.0, "overdue": 0.0, "open_bills": 0})
	return suppliers


@frappe.whitelist()
def get_supplier_detail(supplier: str, company: str) -> dict:
	check_app_permission()
	doc = frappe.get_doc("Supplier", supplier)
	doc.check_permission("read")
	frappe.has_permission("Company", "read", company, throw=True)
	filters = {"supplier": supplier, "company": company}
	invoices = frappe.get_list(
		"Purchase Invoice",
		filters=filters,
		fields=["name", "bill_no", "posting_date", "due_date", "grand_total", "outstanding_amount", "status"],
		order_by="posting_date desc, creation desc",
		limit=100,
	)
	payments = frappe.get_list(
		"Supplier Payment",
		filters=filters,
		fields=["name", "posting_date", "mode_of_payment", "reference_no", "paid_amount", "docstatus"],
		order_by="posting_date desc, creation desc",
		limit=100,
	)
	submitted = [i for i in invoices if i.status not in ("Draft", "Cancelled")]
	return {
		"doc": doc.as_dict(),
		"invoices": invoices,
		"payments": payments,
		"invoiced": flt(sum(flt(i.grand_total) for i in submitted), GL_PRECISION),
		"outstanding": flt(sum(flt(i.outstanding_amount) for i in submitted), GL_PRECISION),
		"overdue": flt(
			sum(flt(i.outstanding_amount) for i in submitted if i.status == "Overdue"), GL_PRECISION
		),
	}


@frappe.whitelist()
def get_purchase_invoice_detail(invoice: str) -> dict:
	check_app_permission()
	doc = frappe.get_doc("Purchase Invoice", invoice)
	doc.check_permission("read")
	payment = frappe.qb.DocType("Supplier Payment")
	reference = frappe.qb.DocType("Supplier Payment Reference")
	payments = (
		frappe.qb.from_(payment)
		.join(reference)
		.on(reference.parent == payment.name)
		.select(
			payment.name,
			payment.posting_date,
			payment.mode_of_payment,
			payment.reference_no,
			payment.docstatus,
			reference.allocated_amount,
		)
		.where((reference.purchase_invoice == invoice) & (payment.docstatus > 0))
		.orderby(payment.posting_date, order=frappe.qb.desc)
		.run(as_dict=True)
	)
	return {
		"doc": doc.as_dict(),
		"payments": payments,
		"assets": frappe.get_all(
			"Asset",
			filters={"purchase_invoice": invoice},
			fields=["name", "asset_name", "status", "gross_purchase_amount"],
			order_by="name asc",
		),
		"account_numbers": dict(
			frappe.get_all(
				"Account",
				filters={"name": ("in", [i.expense_account for i in doc.items])},
				fields=["name", "account_number"],
				as_list=True,
			)
		),
		"can_submit": doc.has_permission("submit"),
		"can_cancel": doc.has_permission("cancel"),
	}


@frappe.whitelist()
def get_asset_detail(asset: str) -> dict:
	check_app_permission()
	doc = frappe.get_doc("Asset", asset)
	doc.check_permission("read")
	schedule = []
	if doc.depreciation_schedule:
		schedule = frappe.get_all(
			"Depreciation Schedule",
			filters={"parent": doc.depreciation_schedule},
			fields=[
				"name",
				"schedule_date",
				"opening_book_value",
				"depreciation_amount",
				"accumulated_depreciation_amount",
				"closing_book_value",
				"journal_entry",
			],
			order_by="idx",
		)
	entries = frappe.get_list(
		"Journal Entry",
		filters={"asset": asset},
		fields=["name", "voucher_type", "posting_date", "total_debit", "docstatus"],
		order_by="posting_date desc, creation desc",
	)
	running_costs = get_running_costs(asset)
	return {
		"doc": doc.as_dict(),
		"schedule": schedule,
		"entries": entries,
		"running_costs": running_costs,
		"running_cost_total": flt(sum(r.amount for r in running_costs), GL_PRECISION),
		"can_submit": doc.has_permission("submit"),
		"can_write": doc.has_permission("write"),
	}



def get_running_costs(asset: str) -> list[dict]:
	"""Expenses booked for an asset, such as fuel for a car: one row per entry and account, newest first."""
	gle = frappe.qb.DocType("GL Entry")
	rows = (
		frappe.qb.from_(gle)
		.select(
			gle.voucher_no.as_("name"),
			gle.posting_date,
			gle.account,
			(Sum(gle.debit) - Sum(gle.credit)).as_("amount"),
		)
		.where((gle.asset == asset) & (gle.is_cancelled == 0) & (gle.voucher_type == "Journal Entry"))
		.groupby(gle.voucher_no, gle.posting_date, gle.account)
		.orderby(gle.posting_date, order=frappe.qb.desc)
		.orderby(gle.voucher_no, order=frappe.qb.desc)
		.run(as_dict=True)
	)
	if not rows:
		return []
	readable = set(
		frappe.get_list("Journal Entry", filters={"name": ("in", {r.name for r in rows})}, pluck="name")
	)
	return [r for r in rows if r.name in readable]

SETTINGS_FIELDS = (
	"approve_purchase_invoice",
	"approve_supplier_payment",
	"approve_journal_entry",
	"approve_recurring_payment",
	"approve_budget",
	"approve_project",
	"allow_self_approval",
	"budget_alert_threshold",
	"notify_budget_exceeded",
	"notify_recurring",
	"notify_bills_due",
	"bill_due_days",
	"send_email",
)


@frappe.whitelist()
def get_settings() -> dict:
	check_app_permission()
	doc = frappe.get_single("Spend Settings")
	doc.check_permission("read")
	return {
		"values": {field: doc.get(field) for field in SETTINGS_FIELDS},
		"can_write": doc.has_permission("write"),
		"has_email_account": bool(
			frappe.db.exists("Email Account", {"enable_outgoing": 1, "default_outgoing": 1})
		),
	}


@frappe.whitelist(methods=["POST"])
def save_settings(values: dict | str) -> dict:
	check_app_permission()
	values = frappe.parse_json(values)
	doc = frappe.get_single("Spend Settings")
	doc.update({field: values[field] for field in SETTINGS_FIELDS if field in values})
	doc.save()
	return get_settings()


@frappe.whitelist(methods=["POST"])
def submit_doc(doctype: str, name: str) -> dict:
	check_app_permission()
	doc = frappe.get_doc(doctype, name)
	doc.submit()
	return doc.as_dict()


@frappe.whitelist(methods=["POST"])
def cancel_doc(doctype: str, name: str) -> dict:
	check_app_permission()
	doc = frappe.get_doc(doctype, name)
	if not doc.has_permission("cancel"):
		frappe.throw(
			_("You are not allowed to cancel {0} {1}").format(_(doctype), name), frappe.PermissionError
		)
	if doc.docstatus != 1:
		frappe.throw(_("Only a submitted {0} can be cancelled").format(_(doctype)))
	doc.cancel()
	return doc.as_dict()


@frappe.whitelist()
def get_item_groups(company: str) -> list[dict]:
	"""Item groups in tree order, with this company's defaults and their item counts."""
	check_app_permission()
	groups = frappe.get_list(
		"Item Group", fields=["name", "parent_item_group", "is_group", "lft", "rgt"], order_by="lft asc"
	)
	defaults = {
		row.parent: row
		for row in frappe.get_all(
			"Item Default",
			filters={"parenttype": "Item Group", "company": company},
			fields=["parent", "expense_account", "buying_cost_center"],
		)
	}
	item = frappe.qb.DocType("Item")
	counts = dict(frappe.qb.from_(item).select(item.item_group, Count("*")).groupby(item.item_group).run())
	for group in groups:
		row = defaults.get(group.name) or {}
		group.expense_account = row.get("expense_account")
		group.buying_cost_center = row.get("buying_cost_center")
		group.items = counts.get(group.name, 0)
	return groups


@frappe.whitelist()
def get_frontend_templates() -> list:
	"""Templates for the Appearance card in Settings."""
	check_app_permission()
	frappe.has_permission("Frontend Template", "read", throw=True)
	return frappe.get_list(
		"Frontend Template",
		fields=["name", "description", "is_active", "is_standard", "color_mode", "primary_color"],
		order_by="is_standard desc, template_name",
	)


@frappe.whitelist(methods=["POST"])
def activate_frontend_template(name: str) -> dict:
	check_app_permission()
	template = frappe.get_doc("Frontend Template", name)
	template.check_permission("write")
	template.is_active = 1
	template.save()
	return get_active_template()
