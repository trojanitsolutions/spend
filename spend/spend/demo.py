# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

"""Demo data: sample masters and transactions that show Spend in use.

Loaded into a company on first setup when the user asks for it. Every record it
inserts is logged as a Demo Data Record, so `clear_demo_data` removes exactly those,
with the entries the system posted for them, and leaves the company's own records alone.
Masters that already exist (a supplier or item of the same name) are used, not logged.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, getdate, today

from spend.spend.accounting import get_fiscal_year
from spend.spend.approval import APPROVED, is_approval_required
from spend.training.sandbox import remove_document

# (group, doctype) to cancel and delete, in order. Cancelling an asset reverses its
# capitalization entry and its depreciation schedule, so those go after it.
TRANSACTION_STAGES = (
	("Supplier Payment", "Supplier Payment"),
	("Journal Entry", "Journal Entry"),
	("Asset", "Asset"),
	("Asset Capitalization", "Journal Entry"),
	("Asset Depreciation Schedule", "Asset Depreciation Schedule"),
	("Purchase Invoice", "Purchase Invoice"),
	("Recurring Payment", "Recurring Payment"),
	("Budget", "Budget"),
	("Task", "Task"),
	("Project", "Project"),
)
# masters go after the transactions and their ledger entries, checking links as they go
MASTER_DOCTYPES = ("Expense Category", "Item", "Item Group", "Supplier", "Cost Center")

COST_CENTERS = ("Administration", "Operations", "Sales and Marketing")

# account name -> annual budget on the company's root cost center
BUDGET = {
	"Administrative Expenses": 400000,
	"Office Rent": 600000,
	"Utilities": 150000,
	"Travel Expenses": 250000,
	"Marketing Expenses": 400000,
	"Software Subscriptions": 200000,
	"Miscellaneous Expenses": 100000,
}

# (category, expense account, sub categories)
CATEGORIES = (
	("Travel", "Travel Expenses", ("Flights", "Hotels")),
	("Office", "Administrative Expenses", ("Supplies", "Cleaning")),
	("Marketing", "Marketing Expenses", ("Online Ads", "Events")),
)

# (supplier, email, phone)
SUPPLIERS = (
	("Acme Office Supplies", "sales@acme-office.example", "+1 555 0101"),
	("Bright Tech Solutions", "billing@brighttech.example", "+1 555 0102"),
	("Skyline Travels", "bookings@skyline.example", "+1 555 0103"),
	("Pixel Marketing Agency", "accounts@pixel.example", "+1 555 0104"),
	("City Utilities Co", "billing@cityutilities.example", "+1 555 0105"),
)

ITEM_GROUPS = ("Office Supplies", "IT Equipment", "Services")

# (item code, item group, uom, standard rate)
ITEMS = (
	("Printer Paper A4", "Office Supplies", "Box", 450),
	("Ink Cartridge", "Office Supplies", "Nos", 1800),
	("Wireless Mouse", "IT Equipment", "Nos", 900),
	("Cloud Hosting", "Services", "Month", 5000),
	("Consulting Services", "Services", "Hour", 2500),
	("Online Ad Campaign", "Services", "Nos", 15000),
	("Flight Ticket", "Services", "Nos", 12000),
	("Hotel Stay", "Services", "Day", 4500),
	("Electricity", "Services", "Month", 8000),
)

PROJECTS = (
	{
		"project_name": "Website Redesign",
		"cost_center": "Sales and Marketing",
		"started": 70,
		"ends_in": 90,
		"accounts": {"Marketing Expenses": 100000, "Software Subscriptions": 50000},
		"categories": (("Marketing", 100000),),
		"tasks": (
			("Agree on the sitemap", "Completed", 100),
			("Design the home page", "Completed", 100),
			("Build the new pages", "Working", 60),
			("Launch campaign", "Open", 0),
		),
	},
	{
		"project_name": "Office Expansion",
		"cost_center": "Administration",
		"started": 50,
		"ends_in": 120,
		"accounts": {"Administrative Expenses": 150000, "Travel Expenses": 50000},
		"categories": (("Office", 100000), ("Travel", 50000)),
		"tasks": (
			("Visit the new premises", "Completed", 100),
			("Furnish the meeting room", "Working", 40),
			("Move the team", "Open", 0),
		),
	},
)

# bills: lines are (item, qty, account, cost center, category, sub category); `paid` is
# "full", a part amount or None, and `due_in` days after the posting date
BILLS = (
	{
		"supplier": "Acme Office Supplies",
		"days_ago": 75,
		"due_in": 30,
		"paid": "full",
		"lines": (
			("Printer Paper A4", 10, "Administrative Expenses", "Administration", "Office", "Supplies"),
			("Ink Cartridge", 4, "Administrative Expenses", "Administration", "Office", "Supplies"),
		),
	},
	{
		"supplier": "Bright Tech Solutions",
		"days_ago": 60,
		"due_in": 30,
		"paid": 10000,
		"lines": (
			("Wireless Mouse", 10, "Administrative Expenses", "Operations", None, None),
			("Cloud Hosting", 2, "Software Subscriptions", "Operations", None, None),
		),
	},
	{
		"supplier": "Pixel Marketing Agency",
		"days_ago": 45,
		"due_in": 15,
		"paid": "full",
		"project": "Website Redesign",
		"lines": (("Online Ad Campaign", 3, "Marketing Expenses", None, "Marketing", "Online Ads"),),
	},
	{
		"supplier": "Bright Tech Solutions",
		"days_ago": 30,
		"due_in": 45,
		"project": "Website Redesign",
		"lines": (("Consulting Services", 12, "Software Subscriptions", None, None, None),),
	},
	{
		"supplier": "Skyline Travels",
		"days_ago": 40,
		"due_in": 15,
		"project": "Office Expansion",
		"lines": (
			("Flight Ticket", 2, "Travel Expenses", None, "Travel", "Flights"),
			("Hotel Stay", 3, "Travel Expenses", None, "Travel", "Hotels"),
		),
	},
	{
		"supplier": "Acme Office Supplies",
		"days_ago": 20,
		"due_in": 30,
		"project": "Office Expansion",
		"lines": (("Printer Paper A4", 20, "Administrative Expenses", None, "Office", "Supplies"),),
	},
	{
		"supplier": "City Utilities Co",
		"days_ago": 10,
		"due_in": 15,
		"lines": (("Electricity", 1, "Utilities", "Administration", None, None),),
	},
	{
		"supplier": "Pixel Marketing Agency",
		"days_ago": 5,
		"due_in": 30,
		"lines": (("Online Ad Campaign", 1, "Marketing Expenses", "Sales and Marketing", None, None),),
	},
)

# (remark, amount, account, cost center, project, category, sub category, days ago)
EXPENSES = (
	("Team lunch", 3200, "Administrative Expenses", "Administration", None, None, None, 70),
	("Taxi to client meeting", 1500, "Travel Expenses", "Operations", None, None, None, 55),
	("Office deep cleaning", 4000, "Administrative Expenses", None, "Office Expansion", "Office", "Cleaning", 35),
	("Trade show booth", 22000, "Marketing Expenses", None, "Website Redesign", "Marketing", "Events", 28),
	("Hotel for site visit", 9000, "Travel Expenses", None, "Office Expansion", "Travel", "Hotels", 12),
	("Internet bill", 2500, "Utilities", "Operations", None, None, None, 3),
)

# (asset, fixed asset account, amount, days ago, useful life in years, cost center, project)
ASSETS = (
	("Laptop for the design team", "Computers", 85000, 90, 3, "Operations", None),
	("Conference Table", "Furniture and Fixtures", 45000, 45, 5, None, "Office Expansion"),
)

RENT = {"title": "Office Rent", "payee": "Skyline Properties", "monthly": 40000}

OPENING_BALANCES = {"Primary Bank": 2000000, "Cash": 50000}


@frappe.whitelist(methods=["POST"])
def clear_company_demo_data(company: str) -> dict:
	from spend.api import check_app_permission

	check_app_permission()
	frappe.has_permission("Company", "write", company, throw=True)
	return clear_demo_data(company)


def has_demo_data(company: str) -> bool:
	return bool(frappe.db.exists("Demo Data Record", {"company": company}))


# ---------------------------------------------------------------- create


def create_demo_data(company: str):
	"""Fill the company with demo masters and transactions dated in the current fiscal year."""
	demo = DemoBuilder(company)
	demo.make_masters()
	demo.make_budget()
	demo.make_projects()
	demo.make_opening_balance()
	demo.make_bills()
	demo.make_expenses()
	demo.make_assets()
	demo.make_rent()


class DemoBuilder:
	def __init__(self, company: str):
		self.company = company
		self.abbr = frappe.db.get_value("Company", company, "abbr")
		self.fiscal_year = ensure_fiscal_year(company)
		self.year_start, self.year_end = frappe.db.get_value(
			"Fiscal Year", self.fiscal_year, ["start_date", "end_date"]
		)
		self.root_cost_center = frappe.db.get_value(
			"Cost Center", {"company": company, "parent_cost_center": ("is", "not set")}
		)
		self.projects = {}

	def days_ago(self, days: int):
		"""A date `days` back, but not before the fiscal year starts."""
		return max(getdate(add_days(today(), -days)), getdate(self.year_start))

	def account(self, account_name: str) -> str:
		return frappe.db.get_value("Account", {"company": self.company, "account_name": account_name})

	def cost_center(self, name: str | None) -> str | None:
		return f"{name} - {self.abbr}" if name else None

	def category(self, name: str | None) -> str | None:
		return f"{name} - {self.abbr}" if name else None

	def insert(self, values: dict, name: str | None = None) -> str:
		"""Insert and log the record; when `name` already exists it is used as it is."""
		if name and frappe.db.exists(values["doctype"], name):
			return name
		doc = frappe.get_doc(values)
		doc.flags.ignore_permissions = True
		doc.insert()
		self.track(doc)
		if is_approval_required(doc.doctype) and not doc.meta.is_submittable:
			doc.db_set("workflow_state", APPROVED)  # set up by the system, not someone's request
		return doc.name

	def submit(self, values: dict) -> str:
		doc = frappe.get_doc(values)
		doc.flags.ignore_permissions = True
		doc.insert()
		self.track(doc)
		if is_approval_required(doc.doctype):
			doc.db_set("workflow_state", APPROVED)
		doc.submit()
		return doc.name

	def track(self, doc):
		frappe.get_doc(
			{
				"doctype": "Demo Data Record",
				"company": self.company,
				"ref_doctype": doc.doctype,
				"ref_name": doc.name,
			}
		).insert(ignore_permissions=True)

	# ---------------------------------------------------------------- masters

	def make_masters(self):
		from spend.purchasing.doctype.item_group.item_group import ROOT

		for name in COST_CENTERS:
			self.insert(
				{
					"doctype": "Cost Center",
					"company": self.company,
					"cost_center_name": name,
					"parent_cost_center": self.root_cost_center,
				},
				self.cost_center(name),
			)
		for category, account, subs in CATEGORIES:
			self.insert(
				{
					"doctype": "Expense Category",
					"company": self.company,
					"category_name": category,
					"is_parent_category": 1,
					"expense_account": self.account(account),
				},
				self.category(category),
			)
			for sub in subs:
				self.insert(
					{
						"doctype": "Expense Category",
						"company": self.company,
						"category_name": sub,
						"parent_category": self.category(category),
						"expense_account": self.account(account),
					},
					self.category(sub),
				)
		for supplier, email, phone in SUPPLIERS:
			self.insert({"doctype": "Supplier", "supplier_name": supplier, "email": email, "phone": phone}, supplier)
		for group in ITEM_GROUPS:
			self.insert({"doctype": "Item Group", "item_group_name": group, "parent_item_group": ROOT}, group)
		for code, group, uom, rate in ITEMS:
			self.insert(
				{
					"doctype": "Item",
					"item_code": code,
					"item_name": code,
					"item_group": group,
					"stock_uom": uom,
					"standard_rate": rate,
				},
				code,
			)

	def make_budget(self):
		self.budget = self.submit(
			{
				"doctype": "Budget",
				"company": self.company,
				"fiscal_year": self.fiscal_year,
				"cost_center": self.root_cost_center,
				"budget_period": "Annual",
				"action_if_exceeded": "Warn",
				"accounts": [
					{"account": self.account(account), "budget_amount": amount}
					for account, amount in BUDGET.items()
				],
			}
		)

	def make_projects(self):
		for project in PROJECTS:
			start = self.days_ago(project["started"])
			name = self.insert(
				{
					"doctype": "Project",
					"company": self.company,
					"project_name": project["project_name"],
					"status": "Open",
					"start_date": start,
					"end_date": add_days(today(), project["ends_in"]),
					"cost_center": self.cost_center(project["cost_center"]),
					"budget": self.budget,
					"budget_amount": sum(project["accounts"].values()),
					"budget_accounts": [
						{"account": self.account(account), "budget_amount": amount}
						for account, amount in project["accounts"].items()
					],
					"expense_categories": [
						{"expense_category": self.category(category), "budget_amount": amount}
						for category, amount in project["categories"]
					],
				}
			)
			self.projects[project["project_name"]] = name
			for subject, status, progress in project["tasks"]:
				self.insert(
					{
						"doctype": "Task",
						"project": name,
						"company": self.company,
						"subject": subject,
						"status": status,
						"progress": progress,
						"exp_start_date": start,
						"exp_end_date": add_days(today(), project["ends_in"]),
					}
				)

	# ---------------------------------------------------------------- transactions

	def make_opening_balance(self):
		"""Capital paid into the bank and cash, so payments leave a positive balance."""
		rows = [{"account": self.account(account), "debit": amount} for account, amount in OPENING_BALANCES.items()]
		rows.append({"account": self.account("Capital Stock"), "credit": sum(OPENING_BALANCES.values())})
		self.submit(
			{
				"doctype": "Journal Entry",
				"voucher_type": "Journal Entry",
				"company": self.company,
				"posting_date": self.year_start,
				"user_remark": _("Opening capital"),
				"accounts": rows,
			}
		)

	def make_bills(self):
		rates = {code: rate for code, _group, _uom, rate in ITEMS}
		for number, bill in enumerate(BILLS, start=1001):
			posting_date = self.days_ago(bill["days_ago"])
			project = self.projects.get(bill.get("project"))
			invoice = self.submit(
				{
					"doctype": "Purchase Invoice",
					"company": self.company,
					"supplier": bill["supplier"],
					"bill_no": f"INV-{number}",
					"bill_date": posting_date,
					"posting_date": posting_date,
					"due_date": add_days(posting_date, bill["due_in"]),
					"project": project,
					"items": [
						{
							"item_code": item,
							"qty": qty,
							"rate": rates[item],
							"expense_account": self.account(account),
							"cost_center": self.cost_center(cost_center),
							"expense_category": self.category(category),
							"expense_sub_category": self.category(sub),
						}
						for item, qty, account, cost_center, category, sub in bill["lines"]
					],
				}
			)
			if bill.get("paid"):
				self.make_payment(invoice, bill)

	def make_payment(self, invoice: str, bill: dict):
		grand_total = frappe.db.get_value("Purchase Invoice", invoice, "grand_total")
		amount = grand_total if bill["paid"] == "full" else bill["paid"]
		self.submit(
			{
				"doctype": "Supplier Payment",
				"company": self.company,
				"supplier": bill["supplier"],
				"mode_of_payment": "Bank Transfer",
				"posting_date": self.days_ago(max(bill["days_ago"] - bill["due_in"], 0)),
				"reference_no": f"TRF-{invoice[-5:]}",
				"paid_from": self.account("Primary Bank"),
				"paid_amount": amount,
				"references": [{"purchase_invoice": invoice, "allocated_amount": amount}],
			}
		)

	def make_expenses(self):
		for remark, amount, account, cost_center, project, category, sub, days in EXPENSES:
			self.submit(
				{
					"doctype": "Journal Entry",
					"voucher_type": "Expense Entry",
					"company": self.company,
					"posting_date": self.days_ago(days),
					"user_remark": remark,
					"accounts": [
						{
							"account": self.account(account),
							"debit": amount,
							"cost_center": self.cost_center(cost_center),
							"project": self.projects.get(project),
							"expense_category": self.category(category),
							"expense_sub_category": self.category(sub),
						},
						{"account": self.account("Cash"), "credit": amount},
					],
				}
			)

	def make_assets(self):
		from spend.spend.depreciation import get_schedules_with_due_rows, make_depreciation_entries

		for asset_name, account, amount, days, life, cost_center, project in ASSETS:
			purchase_date = self.days_ago(days)
			asset = self.submit(
				{
					"doctype": "Asset",
					"company": self.company,
					"asset_name": asset_name,
					"purchase_date": purchase_date,
					"available_for_use_date": purchase_date,
					"gross_purchase_amount": amount,
					"fixed_asset_account": self.account(account),
					"capitalization_credit_account": self.account("Primary Bank"),
					"cost_center": self.cost_center(cost_center),
					"project": self.projects.get(project),
					"calculate_depreciation": 1,
					"depreciation_method": "Straight Line",
					"frequency_of_depreciation": "Monthly",
					"useful_life_years": life,
				}
			)
			for schedule in get_schedules_with_due_rows(today(), asset=asset):
				make_depreciation_entries(schedule, today())

	def make_rent(self):
		"""Monthly rent for the whole fiscal year; the months already due are posted on submit."""
		from spend.purchasing.doctype.recurring_payment.recurring_payment import get_payment_dates

		months = len(get_payment_dates(self.year_start, self.year_end, "Monthly"))
		self.submit(
			{
				"doctype": "Recurring Payment",
				"company": self.company,
				"title": RENT["title"],
				"payee": RENT["payee"],
				"expense_account": self.account("Office Rent"),
				"paid_from": self.account("Primary Bank"),
				"budget": self.budget,
				"cost_center": self.cost_center("Administration"),
				"from_date": self.year_start,
				"to_date": self.year_end,
				"frequency": "Monthly",
				"total_amount": RENT["monthly"] * months,
			}
		)


def ensure_fiscal_year(company: str) -> str:
	"""The fiscal year of today, created as the calendar year when there is none."""
	if fiscal_year := get_fiscal_year(today(), throw=False):
		return fiscal_year
	year = getdate().year
	name = str(year)
	if frappe.db.exists("Fiscal Year", name):
		name = f"{year} ({frappe.db.get_value('Company', company, 'abbr')})"
	fiscal_year = frappe.get_doc(
		{
			"doctype": "Fiscal Year",
			"fiscal_year_name": name,
			"start_date": f"{year}-01-01",
			"end_date": f"{year}-12-31",
		}
	)
	fiscal_year.insert(ignore_permissions=True)
	return fiscal_year.name


# ---------------------------------------------------------------- clear


def clear_demo_data(company: str) -> dict:
	"""Cancel and delete what demo data created in the company, with the entries posted for it.

	A demo record that the company's own records still use (say a demo supplier on a real
	bill) is reported, not raised, and stays logged so it can be cleared later."""
	records = frappe.get_all(
		"Demo Data Record", filters={"company": company}, fields=["ref_doctype", "ref_name"]
	)
	names = defaultdict(set)
	for record in records:
		names[record.ref_doctype].add(record.ref_name)
	add_system_postings(names)

	removed: set[tuple[str, str]] = set()
	failed: dict[tuple[str, str], str] = {}
	for _pass in range(3):
		failed.clear()
		for group, doctype in TRANSACTION_STAGES:
			for name in sort_for_removal(doctype, names[group]):
				if (doctype, name) not in removed and remove_document(doctype, name, failed):
					removed.add((doctype, name))
		if not failed:
			break

	for doctype in {doctype for _group, doctype in TRANSACTION_STAGES}:
		vouchers = [name for dt, name in removed if dt == doctype]
		if vouchers:
			frappe.db.delete("GL Entry", {"voucher_type": doctype, "voucher_no": ("in", vouchers)})

	for doctype in MASTER_DOCTYPES:
		for name in sort_for_removal(doctype, names[doctype]):
			if remove_document(doctype, name, failed, force=False):
				removed.add((doctype, name))

	for doctype, name in removed:
		frappe.db.delete("Demo Data Record", {"company": company, "ref_doctype": doctype, "ref_name": name})
	return {
		"deleted": len(removed),
		"failed": [{"doctype": dt, "name": name, "error": error} for (dt, name), error in failed.items()],
	}


def add_system_postings(names: dict):
	"""Depreciation schedules of demo assets, and the entries posted for demo assets and rent."""
	if assets := list(names["Asset"]):
		names["Asset Depreciation Schedule"].update(
			frappe.get_all("Asset Depreciation Schedule", filters={"asset": ("in", assets)}, pluck="name")
		)
		for name, voucher_type in frappe.get_all(
			"Journal Entry", filters={"asset": ("in", assets)}, fields=["name", "voucher_type"], as_list=True
		):
			names["Asset Capitalization" if voucher_type == "Asset Capitalization" else "Journal Entry"].add(name)
	if payments := list(names["Recurring Payment"]):
		names["Journal Entry"].update(
			frappe.get_all("Journal Entry", filters={"recurring_payment": ("in", payments)}, pluck="name")
		)


def sort_for_removal(doctype: str, names: set) -> list[str]:
	"""Newest entries first (depreciation is reversed newest first), sub categories before their parents."""
	existing = [n for n in names if frappe.db.exists(doctype, n)]
	if doctype == "Journal Entry":
		dates = dict(
			frappe.get_all(
				doctype, filters={"name": ("in", existing or [""])}, fields=["name", "posting_date"], as_list=True
			)
		)
		return sorted(existing, key=lambda n: (dates[n], n), reverse=True)
	if doctype == "Expense Category":
		parents = set(
			frappe.get_all(
				doctype, filters={"name": ("in", existing or [""]), "is_parent_category": 1}, pluck="name"
			)
		)
		return sorted(existing, key=lambda n: n in parents)
	return sorted(existing)
