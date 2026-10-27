# Copyright (c) 2026, Trojan IT Solutions and Contributors
# See license.txt

"""Fixtures shared by the spend test suites. Everything is created inside the
test transaction and rolled back by IntegrationTestCase."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

TEST_COMPANY = "_Test Spend Company"
TEST_ABBR = "_TSC"


def ensure_fiscal_year(year: int) -> str:
	start, end = getdate(f"{year}-01-01"), getdate(f"{year}-12-31")
	existing = frappe.db.get_value(
		"Fiscal Year", {"start_date": ("<=", start), "end_date": (">=", end), "disabled": 0}
	)
	if existing:
		return existing
	return (
		frappe.get_doc(
			{
				"doctype": "Fiscal Year",
				"fiscal_year_name": f"_Test FY {year}",
				"start_date": start,
				"end_date": end,
			}
		)
		.insert()
		.name
	)


def make_company(name=TEST_COMPANY, abbr=TEST_ABBR):
	if frappe.db.exists("Company", name):
		return frappe.get_doc("Company", name)
	if not frappe.db.exists("Currency", "INR"):
		frappe.get_doc({"doctype": "Currency", "currency_name": "INR", "enabled": 1}).insert()
	return frappe.get_doc(
		{"doctype": "Company", "company_name": name, "abbr": abbr, "default_currency": "INR"}
	).insert()


def account(name, abbr=TEST_ABBR):
	return f"{name} - {abbr}"


def make_cost_center(name, parent=None, is_group=0, company=TEST_COMPANY, abbr=TEST_ABBR):
	full = f"{name} - {abbr}"
	if frappe.db.exists("Cost Center", full):
		return full
	return (
		frappe.get_doc(
			{
				"doctype": "Cost Center",
				"cost_center_name": name,
				"company": company,
				"parent_cost_center": parent or f"{company} - {abbr}",
				"is_group": is_group,
			}
		)
		.insert()
		.name
	)


def make_journal_entry(
	debit_account, credit_account, amount, posting_date, cost_center=None, submit=True, **kw
):
	je = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": kw.pop("voucher_type", "Expense Entry"),
			"company": kw.pop("company", TEST_COMPANY),
			"posting_date": posting_date,
			"accounts": [
				{"account": debit_account, "debit": amount, "cost_center": cost_center},
				{"account": credit_account, "credit": amount},
			],
			**kw,
		}
	).insert()
	if submit:
		je.submit()
	return je


def make_asset(submit=True, **kw):
	values = {
		"doctype": "Asset",
		"asset_name": "_Test Laptop",
		"company": TEST_COMPANY,
		"purchase_date": "2025-01-01",
		"available_for_use_date": "2025-01-01",
		"gross_purchase_amount": 120000,
		"salvage_value": 0,
		"calculate_depreciation": 1,
		"depreciation_method": "Straight Line",
		"frequency_of_depreciation": "Monthly",
		"useful_life_years": 1,
		"capitalization_credit_account": account("Creditors"),
	}
	values.update(kw)
	asset = frappe.get_doc(values).insert()
	if submit:
		asset.submit()
	return asset


def make_supplier(name="_Test Supplier", **kw):
	if frappe.db.exists("Supplier", name):
		return frappe.get_doc("Supplier", name)
	return frappe.get_doc({"doctype": "Supplier", "supplier_name": name, **kw}).insert()


def make_item(code="_Test Item", **kw):
	if frappe.db.exists("Item", code):
		return frappe.get_doc("Item", code)
	return frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": code, **kw}).insert()


def make_purchase_invoice(items=None, submit=True, **kw):
	"""Bill from _Test Supplier. `items` are (expense account name, amount[, project]) tuples."""
	items = items or [("Office Rent", 5000)]
	values = {
		"doctype": "Purchase Invoice",
		"supplier": make_supplier().name,
		"company": TEST_COMPANY,
		"posting_date": "2025-03-01",
		"due_date": "2025-03-31",
		"items": [
			{
				"item_code": make_item().name,
				"description": name,
				"expense_account": account(name),
				"qty": 1,
				"rate": amount,
				"project": project[0] if project else None,
			}
			for name, amount, *project in items
		],
	}
	values.update(kw)
	invoice = frappe.get_doc(values).insert()
	if submit:
		invoice.submit()
	return invoice


def make_project(name="_Test Project", budget=0, action="Warn", accounts=None, budget_doc=None, **kw):
	"""Project of the test company. `accounts` are (expense account name, limit) pairs.

	Without `budget_doc`, the project takes its share from a large Budget
	that covers every expense account (see `get_project_budget`).
	"""
	company = kw.pop("company", TEST_COMPANY)
	return frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": name,
			"company": company,
			"budget": budget_doc or get_project_budget(company),
			"budget_amount": budget,
			"action_if_exceeded": action,
			"budget_accounts": [
				{"account": account(acc), "budget_amount": limit} for acc, limit in accounts or []
			],
			**kw,
		}
	).insert()


def get_project_budget(company=TEST_COMPANY, year=2025) -> str:
	"""A submitted Budget for `year` big enough for any test, on a group cost center of its own."""
	abbr = frappe.db.get_value("Company", company, "abbr")
	cost_center = make_cost_center("_Test Projects", is_group=1, company=company, abbr=abbr)
	fiscal_year = ensure_fiscal_year(year)
	existing = frappe.db.get_value(
		"Budget", {"cost_center": cost_center, "fiscal_year": fiscal_year, "docstatus": 1}
	)
	if existing:
		return existing
	accounts = frappe.get_all(
		"Account", filters={"company": company, "root_type": "Expense", "is_group": 0}, pluck="name"
	)
	budget = frappe.get_doc(
		{
			"doctype": "Budget",
			"company": company,
			"fiscal_year": fiscal_year,
			"cost_center": cost_center,
			"action_if_exceeded": "Ignore",
			"accounts": [{"account": acc, "budget_amount": 10**9} for acc in accounts],
		}
	)
	budget.flags.ignore_permissions = True
	budget.insert()
	budget.submit()
	return budget.name


def get_recurring_cost_center(company=TEST_COMPANY) -> str:
	"""A cost center under the test project Budgets, for recurring payments without a project."""
	abbr = frappe.db.get_value("Company", company, "abbr")
	parent = make_cost_center("_Test Projects", is_group=1, company=company, abbr=abbr)
	return make_cost_center("_Test Recurring", parent=parent, company=company, abbr=abbr)


def make_supplier_payment(allocations, submit=True, **kw):
	"""Pay bills from Cash. `allocations` are (invoice name, amount) pairs."""
	first = frappe.get_doc("Purchase Invoice", allocations[0][0])
	values = {
		"doctype": "Supplier Payment",
		"supplier": first.supplier,
		"company": first.company,
		"posting_date": "2025-03-15",
		"paid_from": account("Cash"),
		"paid_amount": sum(amount for _name, amount in allocations),
		"references": [
			{"purchase_invoice": name, "allocated_amount": amount} for name, amount in allocations
		],
	}
	values.update(kw)
	payment = frappe.get_doc(values).insert()
	if submit:
		payment.submit()
	return payment


def make_recurring_payment(total=1200, from_date="2025-01-01", to_date="2025-12-31", submit=True, **kw):
	"""Monthly Office Rent paid from Cash unless overridden.

	Without a project or budget, it takes from the test Budget of the `from_date` year.
	"""
	if not (kw.get("project") or kw.get("budget")):
		kw["budget"] = get_project_budget(year=getdate(from_date).year)
	kw.setdefault("cost_center", get_recurring_cost_center())
	values = {
		"doctype": "Recurring Payment",
		"title": "_Test Rent",
		"company": TEST_COMPANY,
		"expense_account": account("Office Rent"),
		"paid_from": account("Cash"),
		"from_date": from_date,
		"to_date": to_date,
		"frequency": "Monthly",
		"total_amount": total,
	}
	values.update(kw)
	doc = frappe.get_doc(values).insert()
	if submit:
		doc.submit()
	return doc


def set_approvals(on: bool):
	"""Turn every approval on or off. Only Spend Settings changes, so the workflows stay as they are."""
	from spend.spend.approval import APPROVAL_DOCTYPES

	frappe.db.set_single_value("Spend Settings", dict.fromkeys(APPROVAL_DOCTYPES.values(), int(on)))


def make_user(email, roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	user = frappe.get_doc("User", email)
	user.add_roles(*roles)
	return email


def setup_test_data():
	for year in (2024, 2025, 2026, 2027, 2028, 2029, 2030):
		ensure_fiscal_year(year)
	set_approvals(False)
	company = make_company()
	get_project_budget()
	get_recurring_cost_center()
	return company


class SpendTestCase(IntegrationTestCase):
	"""Shared company and fiscal years per class; each test runs in its own savepoint."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = setup_test_data()

	def setUp(self):
		frappe.db.savepoint("spend_test")
		self.addCleanup(frappe.db.rollback, save_point="spend_test")
