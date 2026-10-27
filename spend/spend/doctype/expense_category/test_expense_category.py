# Copyright (c) 2026, Trojan IT Solutions and Contributors
# See license.txt

import frappe

from spend.spend.doctype.budget.budget import BudgetExceededError
from spend.spend.doctype.project.project import get_project_summary
from spend.spend.expense_category import get_category_account, get_category_monthly
from spend.tests.utils import (
	TEST_COMPANY,
	SpendTestCase,
	account,
	ensure_fiscal_year,
	make_project,
	make_purchase_invoice,
	make_recurring_payment,
)

IGNORE_TEST_RECORD_DEPENDENCIES = ["Company", "Account", "Cost Center", "Fiscal Year"]


def make_category(name, parent=None, expense_account=None):
	return frappe.get_doc(
		{
			"doctype": "Expense Category",
			"category_name": name,
			"company": TEST_COMPANY,
			"is_parent_category": 0 if parent else 1,
			"parent_category": parent,
			"expense_account": account(expense_account) if expense_account else None,
		}
	).insert()


def book(project, amount, category, sub_category=None, posting_date="2025-02-01", submit=True):
	"""An expense entry booked from the project, with the account of its category."""
	je = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Expense Entry",
			"company": TEST_COMPANY,
			"posting_date": posting_date,
			"accounts": [
				{
					"account": get_category_account(category, sub_category),
					"project": project,
					"expense_category": category,
					"expense_sub_category": sub_category,
					"debit": amount,
				},
				{"account": account("Cash"), "credit": amount},
			],
		}
	).insert()
	if submit:
		je.submit()
	return je


class IntegrationTestExpenseCategory(SpendTestCase):
	def setUp(self):
		super().setUp()
		self.utilities = make_category("_Test Utilities", expense_account="Utilities")
		self.power = make_category("_Test Power", parent=self.utilities.name)
		self.water = make_category("_Test Water", parent=self.utilities.name, expense_account="Office Rent")
		self.rent = make_category("_Test Rent Category", expense_account="Office Rent")

	def project(self, rows=(), action="Warn", **kw):
		return make_project(
			action=action,
			start_date="2025-01-01",
			end_date="2025-12-31",
			expense_categories=[
				{"expense_category": c, "expense_sub_category": s, "budget_amount": b} for c, s, b in rows
			],
			**kw,
		)

	def test_account_comes_from_sub_category_or_category(self):
		self.assertEqual(get_category_account(self.utilities.name, self.power.name), account("Utilities"))
		self.assertEqual(get_category_account(self.utilities.name, self.water.name), account("Office Rent"))
		self.assertEqual(get_category_account(self.rent.name), account("Office Rent"))

	def test_parent_rules(self):
		# a sub category needs a parent, and only a parent category can be one
		orphan = frappe.get_doc(
			{"doctype": "Expense Category", "category_name": "_Test Orphan", "company": TEST_COMPANY}
		)
		self.assertRaises(frappe.ValidationError, orphan.insert)
		self.assertRaises(frappe.ValidationError, make_category, "_Test Deep", parent=self.power.name)

		# a parent with sub categories stays a parent
		self.utilities.is_parent_category = 0
		self.utilities.parent_category = self.rent.name
		self.assertRaises(frappe.ValidationError, self.utilities.save)

	def test_booking_checks_the_category(self):
		project = self.project()
		# any category on a project without category rows; the category is filled from the sub category
		je = book(project.name, 100, None, self.power.name)
		self.assertEqual(je.accounts[0].expense_category, self.utilities.name)
		self.assertRaisesRegex(
			frappe.ValidationError,
			"not a sub category",
			book,
			project.name,
			100,
			self.rent.name,
			self.power.name,
		)
		self.assertRaisesRegex(
			frappe.ValidationError, "is a sub category", book, project.name, 100, self.power.name
		)

		limited = self.project([(self.utilities.name, self.water.name, 0)], name="_Test Limited")
		book(limited.name, 100, self.utilities.name, self.water.name)
		for category, sub in ((self.rent.name, None), (self.utilities.name, self.power.name)):
			self.assertRaisesRegex(
				frappe.ValidationError,
				"not one of the expense categories",
				book,
				limited.name,
				100,
				category,
				sub,
			)

	def test_search_offers_the_project_categories(self):
		from spend.spend.doctype.expense_category.expense_category import get_categories

		def search(**filters):
			rows = get_categories(
				"Expense Category", "_Test", "name", 0, 20, {"company": TEST_COMPANY, **filters}
			)
			return {name for name, _parent in rows}

		self.assertEqual(search(), {self.utilities.name, self.rent.name})
		self.assertEqual(search(parent_category=self.utilities.name), {self.power.name, self.water.name})
		self.assertEqual(search(parent_category=""), set())

		project = self.project([(self.utilities.name, self.water.name, 0)])
		self.assertEqual(search(project=project.name), {self.utilities.name})
		self.assertEqual(search(project=project.name, parent_category=self.utilities.name), {self.water.name})

	def test_category_budget_stops_or_warns(self):
		project = self.project([(self.utilities.name, None, 1000)], action="Stop")
		book(project.name, 800, self.utilities.name, self.power.name)
		self.assertRaises(BudgetExceededError, book, project.name, 300, self.utilities.name, self.water.name)

		bill = make_purchase_invoice([("Utilities", 300, project.name)], submit=False)
		bill.items[0].expense_category = self.utilities.name
		bill.save()
		self.assertRaises(BudgetExceededError, bill.submit)

		project.action_if_exceeded = "Warn"
		project.save()
		book(project.name, 300, self.utilities.name)
		summary = get_project_summary(project.name)["categories"][0]
		self.assertEqual(summary["charged"], 1100)
		self.assertEqual(summary["remaining"], -100)

	def test_recurring_payment_fits_in_the_category(self):
		project = self.project([(self.rent.name, None, 1000)], action="Stop", name="_Test Recurring")
		book(project.name, 400, self.rent.name)
		kw = {"project": project.name, "expense_category": self.rent.name, "submit": False}
		self.assertRaisesRegex(frappe.ValidationError, "has .* free", make_recurring_payment, total=700, **kw)
		payment = make_recurring_payment(total=600, **kw)
		self.assertEqual(payment.expense_category, self.rent.name)

	def test_project_category_budgets(self):
		self.assertRaisesRegex(
			frappe.ValidationError,
			"more than the Total Budget",
			self.project,
			[(self.utilities.name, None, 600), (self.rent.name, None, 600)],
			budget=1000,
		)
		self.assertRaisesRegex(
			frappe.ValidationError,
			"more than its",
			self.project,
			[(self.utilities.name, None, 500), (self.utilities.name, self.power.name, 600)],
		)
		self.assertRaisesRegex(
			frappe.ValidationError,
			"repeated",
			self.project,
			[(self.rent.name, None, 1), (self.rent.name, None, 2)],
		)

	def test_monthly_charge(self):
		project = self.project()
		book(project.name, 100, self.utilities.name, self.power.name, "2025-02-03")
		book(project.name, 50, self.utilities.name, None, "2025-02-20")
		book(project.name, 70, self.rent.name, None, "2025-03-05")
		book(project.name, 999, self.rent.name, None, "2025-03-06").cancel()

		entries = get_category_monthly("2025-01-01", "2025-12-31", project=project.name)
		amounts = {(e.category, e.sub_category, e.month): e.amount for e in entries}
		self.assertEqual(amounts[(self.utilities.name, self.power.name, "2025-02")], 100)
		self.assertEqual(amounts[(self.utilities.name, None, "2025-02")], 50)
		self.assertEqual(amounts[(self.rent.name, None, "2025-03")], 70)

		monthly = get_project_summary(project.name)["monthly"]
		self.assertEqual(len(monthly["months"]), 12)
		rows = {(r["category"], r["sub_category"]): r for r in monthly["rows"]}
		self.assertEqual(rows[(self.utilities.name, None)]["months"]["2025-02"], 150)
		self.assertEqual(rows[(self.utilities.name, self.power.name)]["total"], 100)
		self.assertEqual(rows[(self.rent.name, None)]["total"], 70)
		self.assertEqual(
			[(r["category"], r["sub_category"]) for r in monthly["rows"]],
			[(self.rent.name, None), (self.utilities.name, None), (self.utilities.name, self.power.name)],
		)  # each category is followed by its sub categories

	def test_monthly_report(self):
		from spend.spend.report.project_category_monthly.project_category_monthly import execute

		project = self.project()
		book(project.name, 100, self.utilities.name, self.power.name, "2025-02-03")
		columns, data, _, chart, summary = execute(
			{"company": TEST_COMPANY, "project": project.name, "fiscal_year": ensure_fiscal_year(2025)}
		)
		self.assertEqual(len(columns), 2 + 12 + 1)
		self.assertEqual(
			[(d["category"], d["indent"]) for d in data], [(self.utilities.name, 0), (self.power.name, 1)]
		)
		self.assertEqual(data[1]["2025_02"], 100)
		self.assertEqual(summary[0]["value"], 100)
		self.assertTrue(chart)
