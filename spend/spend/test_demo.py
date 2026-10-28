# Copyright (c) 2026, Trojan IT Solutions and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from spend.spend.approval import APPROVED, is_approval_required
from spend.spend.demo import clear_demo_data, create_demo_data, has_demo_data

DEMO_COMPANY = "_Test Demo Company"
DEMO_ABBR = "_TDC"
TRANSACTIONS = ("Purchase Invoice", "Supplier Payment", "Journal Entry", "Asset", "Budget", "Recurring Payment")


class TestDemoData(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Currency", "INR"):
			frappe.get_doc({"doctype": "Currency", "currency_name": "INR", "enabled": 1}).insert()
		cls.company = (
			frappe.get_doc(
				{
					"doctype": "Company",
					"company_name": DEMO_COMPANY,
					"abbr": DEMO_ABBR,
					"default_currency": "INR",
					"create_default_accounts": 1,
				}
			)
			.insert()
			.name
		)
		create_demo_data(cls.company)

	def setUp(self):
		# the class rolls back only at the end, so each test undoes its own clearing
		frappe.db.savepoint("demo_test")

	def tearDown(self):
		frappe.db.rollback(save_point="demo_test")

	def test_creates_posted_demo_records(self):
		self.assertTrue(has_demo_data(self.company))
		for doctype in TRANSACTIONS:
			self.assertTrue(
				frappe.db.exists(doctype, {"company": self.company, "docstatus": 1}), f"no submitted {doctype}"
			)
		self.assertTrue(frappe.db.exists("Project", {"company": self.company}))
		self.assertTrue(frappe.db.exists("Task", {"company": self.company}))
		debit, credit = frappe.db.sql(
			"select sum(debit), sum(credit) from `tabGL Entry` where company=%s and is_cancelled=0",
			self.company,
		)[0]
		self.assertGreater(debit, 0)
		self.assertAlmostEqual(debit, credit, places=2)

	def test_clear_removes_demo_records_only(self):
		own_supplier = frappe.get_doc({"doctype": "Supplier", "supplier_name": "_Test Own Supplier"}).insert().name

		result = clear_demo_data(self.company)

		self.assertEqual(result["failed"], [])
		self.assertFalse(has_demo_data(self.company))
		for doctype in (*TRANSACTIONS, "Project", "Task", "Expense Category", "GL Entry"):
			self.assertFalse(frappe.db.exists(doctype, {"company": self.company}), f"{doctype} left behind")
		self.assertFalse(frappe.db.exists("Supplier", "Acme Office Supplies"))
		self.assertFalse(frappe.db.exists("Cost Center", f"Operations - {DEMO_ABBR}"))
		self.assertTrue(frappe.db.exists("Supplier", own_supplier))
		self.assertTrue(frappe.db.exists("Cost Center", f"Main - {DEMO_ABBR}"))

	def test_demo_master_in_use_is_kept(self):
		bill = frappe.get_doc(
			{
				"doctype": "Purchase Invoice",
				"company": self.company,
				"supplier": "Acme Office Supplies",
				"posting_date": today(),
				"due_date": add_days(today(), 30),
				"items": [
					{
						"item_code": "Printer Paper A4",
						"qty": 1,
						"rate": 100,
						"expense_account": frappe.db.get_value(
							"Account", {"company": self.company, "account_name": "Administrative Expenses"}
						),
						"cost_center": f"Administration - {DEMO_ABBR}",
					}
				],
			}
		).insert()
		if is_approval_required("Purchase Invoice"):
			bill.db_set("workflow_state", APPROVED)
		bill.submit()

		result = clear_demo_data(self.company)

		failed = {(f["doctype"], f["name"]) for f in result["failed"]}
		self.assertIn(("Supplier", "Acme Office Supplies"), failed)
		self.assertEqual(frappe.db.get_value("Purchase Invoice", bill.name, "docstatus"), 1)
		self.assertTrue(
			frappe.db.exists(
				"Demo Data Record",
				{"company": self.company, "ref_doctype": "Supplier", "ref_name": "Acme Office Supplies"},
			)
		)
