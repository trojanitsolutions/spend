# Copyright (c) 2026, Trojan IT Solutions and Contributors
# See license.txt

import frappe

from spend.spend.setup import setup_company
from spend.tests.utils import SpendTestCase, make_user

MANAGER = "_spend_setup_manager@example.com"
GM = "_spend_setup_gm@example.com"


class TestSetupCompany(SpendTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_user(MANAGER, ["Accounts Manager"])
		make_user(GM, ["General Manager"])

	def setUp(self):
		super().setUp()
		self.addCleanup(frappe.set_user, "Administrator")
		# a new install: no companies yet (rolled back after each test)
		frappe.db.delete("Company")

	def test_first_company_is_created_with_its_chart(self):
		frappe.set_user(MANAGER)
		name = setup_company("Acme Global Traders", "agt", "INR")["name"]

		company = frappe.get_doc("Company", name)
		self.assertEqual(company.abbr, "AGT")
		self.assertEqual(company.default_currency, "INR")
		self.assertEqual(company.default_cash_account, "Cash - AGT")
		self.assertTrue(frappe.db.exists("Cost Center", {"company": name, "is_group": 0}))
		self.assertEqual(frappe.db.get_single_value("System Settings", "default_app"), "spend")
		self.assertEqual(frappe.defaults.get_user_default("Company"), name)

		with self.assertRaises(frappe.ValidationError):
			setup_company("Second Company", "SC", "INR")

	def test_user_who_cannot_create_a_company(self):
		frappe.set_user(GM)
		with self.assertRaises(frappe.PermissionError):
			setup_company("Acme Global Traders", "AGT", "INR")
