# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

"""Install-time setup: roles and the standard chart of accounts for new companies."""

import frappe
from frappe import _

ROLES = ("Accounts Manager", "General Manager")

# (account_number, account_name, account_type, children). Root entries carry their root type.
STANDARD_CHART = [
	(
		"1000",
		"Application of Funds (Assets)",
		"Asset",
		[
			(
				"1100",
				"Current Assets",
				None,
				[
					("1110", "Cash In Hand", None, [("1111", "Cash", "Cash", None)]),
					("1120", "Bank Accounts", None, [("1121", "Primary Bank", "Bank", None)]),
					("1130", "Accounts Receivable", None, [("1131", "Debtors", "Receivable", None)]),
				],
			),
			(
				"1200",
				"Fixed Assets",
				None,
				[
					("1210", "Furniture and Fixtures", "Fixed Asset", None),
					("1220", "Office Equipment", "Fixed Asset", None),
					("1230", "Computers", "Fixed Asset", None),
					("1240", "Vehicles", "Fixed Asset", None),
					("1290", "Accumulated Depreciation", "Accumulated Depreciation", None),
				],
			),
		],
	),
	(
		"2000",
		"Source of Funds (Liabilities)",
		"Liability",
		[
			(
				"2100",
				"Current Liabilities",
				None,
				[
					("2110", "Accounts Payable", None, [("2111", "Creditors", "Payable", None)]),
					("2120", "Duties and Taxes", None, [("2121", "Taxes Payable", "Tax", None)]),
				],
			),
		],
	),
	(
		"3000",
		"Equity",
		"Equity",
		[("3100", "Capital Stock", "Equity", None), ("3200", "Retained Earnings", "Equity", None)],
	),
	(
		"4000",
		"Income",
		"Income",
		[
			("4100", "Direct Income", None, [("4110", "Sales", "Income Account", None)]),
			("4200", "Indirect Income", None, [("4210", "Other Income", "Income Account", None)]),
		],
	),
	(
		"5000",
		"Expenses",
		"Expense",
		[
			("5100", "Direct Expenses", None, [("5110", "Cost of Goods Sold", "Cost of Goods Sold", None)]),
			(
				"5200",
				"Indirect Expenses",
				None,
				[
					("5201", "Administrative Expenses", "Expense Account", None),
					("5202", "Depreciation", "Depreciation", None),
					("5203", "Office Rent", "Expense Account", None),
					("5204", "Utilities", "Expense Account", None),
					("5205", "Salaries", "Expense Account", None),
					("5206", "Travel Expenses", "Expense Account", None),
					("5207", "Marketing Expenses", "Expense Account", None),
					("5208", "Software Subscriptions", "Expense Account", None),
					("5209", "Miscellaneous Expenses", "Expense Account", None),
					("5299", "Round Off", "Round Off", None),
				],
			),
		],
	),
]


def iter_standard_chart(nodes=STANDARD_CHART):
	"""Yield (account_number, account_name) for every account in the standard chart."""
	for number, name, _type, children in nodes:
		yield number, name
		yield from iter_standard_chart(children or [])


# Company field -> standard account name
STANDARD_DEFAULTS = {
	"default_cash_account": "Cash",
	"default_payable_account": "Creditors",
	"default_expense_account": "Miscellaneous Expenses",
	"fixed_asset_account": "Office Equipment",
	"accumulated_depreciation_account": "Accumulated Depreciation",
	"depreciation_expense_account": "Depreciation",
}


def after_install():
	from spend.spend.approval import setup_workflows
	from spend.spend.notifications import setup_notification_types

	create_roles()
	setup_notification_types()
	frappe.get_single("Spend Settings").save()
	setup_workflows()
	setup_items()


# (UOM, must be whole number) created with the app
UOMS = (
	("Nos", 1),
	("Unit", 1),
	("Box", 1),
	("Pair", 1),
	("Set", 1),
	("Bag", 1),
	("Kg", 0),
	("Gram", 0),
	("Tonne", 0),
	("Litre", 0),
	("Meter", 0),
	("Square Meter", 0),
	("Cubic Meter", 0),
	("Hour", 0),
	("Day", 0),
	("Month", 0),
)


def setup_items():
	from spend.purchasing.doctype.item_group.item_group import make_root

	for uom, whole in UOMS:
		if not frappe.db.exists("UOM", uom):
			frappe.get_doc({"doctype": "UOM", "uom_name": uom, "must_be_whole_number": whole}).insert(
				ignore_permissions=True
			)
	make_root()


@frappe.whitelist(methods=["POST"])
def setup_company(company_name: str, abbr: str, currency: str, demo_data: bool = False) -> dict:
	"""First run: create the first company with its chart of accounts, and make Spend the
	app every user lands on after login. With `demo_data` the company is filled with sample
	records; if that fails the company is still created and the error is returned."""
	from spend.api import check_app_permission

	check_app_permission()
	frappe.has_permission("Company", "create", throw=True)
	if frappe.db.count("Company"):
		frappe.throw(_("Spend is already set up"))

	company = frappe.get_doc(
		{
			"doctype": "Company",
			"company_name": (company_name or "").strip(),
			"abbr": abbr,
			"default_currency": currency,
			"create_default_accounts": 1,
		}
	).insert()
	frappe.db.set_single_value("System Settings", "default_app", "spend")
	frappe.defaults.set_user_default("company", company.name)
	result = {"name": company.name}
	if frappe.utils.cint(demo_data):
		result["demo_error"] = load_demo_data(company.name)
	return result


def load_demo_data(company: str) -> str | None:
	from spend.spend.demo import create_demo_data

	frappe.db.savepoint("demo_data")
	try:
		create_demo_data(company)
	except Exception as e:
		frappe.db.rollback(save_point="demo_data")
		frappe.clear_messages()
		frappe.log_error(title=_("Demo data could not be created for {0}").format(company))
		return str(e) or e.__class__.__name__


def create_roles():
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
				ignore_permissions=True
			)


def create_default_chart(company):
	"""Create the standard account tree and cost centers, then fill the company defaults."""
	if frappe.db.exists("Account", {"company": company.name}):
		return

	for number, root_name, root_type, children in STANDARD_CHART:
		_create_account(company.name, number, root_name, None, None, children, root_type=root_type)

	root_cc = _create_cost_center(company.name, company.company_name, None, is_group=1)
	main_cc = _create_cost_center(company.name, "Main", root_cc)

	defaults = {
		field: frappe.db.get_value("Account", {"company": company.name, "account_name": account_name})
		for field, account_name in STANDARD_DEFAULTS.items()
	}
	defaults["default_cost_center"] = main_cc
	company.db_set(defaults)


def _create_account(company, account_number, account_name, account_type, parent, children, root_type=None):
	account = frappe.get_doc(
		{
			"doctype": "Account",
			"company": company,
			"account_name": account_name,
			"account_number": account_number,
			"parent_account": parent,
			"is_group": 1 if children is not None else 0,
			"account_type": account_type if account_type and children is None else None,
			"root_type": root_type,
		}
	)
	account.flags.ignore_permissions = True
	account.insert()
	for child_number, child_name, child_type, grandchildren in children or []:
		_create_account(company, child_number, child_name, child_type, account.name, grandchildren)
	return account.name


def _create_cost_center(company, name, parent, is_group=0):
	cost_center = frappe.get_doc(
		{
			"doctype": "Cost Center",
			"company": company,
			"cost_center_name": name,
			"parent_cost_center": parent,
			"is_group": is_group,
		}
	)
	cost_center.flags.ignore_permissions = True
	cost_center.insert()
	return cost_center.name
