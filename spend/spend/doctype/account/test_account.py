# Copyright (c) 2026, Trojan IT Solutions and Contributors
# See license.txt

import frappe

from spend.spend.accounting import get_balance
from spend.tests.utils import (
	TEST_COMPANY,
	SpendTestCase,
	account,
	make_company,
	make_journal_entry,
	setup_test_data,
)

IGNORE_TEST_RECORD_DEPENDENCIES = ["Company", "Account", "Currency"]


class IntegrationTestAccount(SpendTestCase):
	def new_account(self, name, parent, **kw):
		return frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": name,
				"company": TEST_COMPANY,
				"parent_account": parent,
				**kw,
			}
		)

	def test_name_includes_company_abbreviation(self):
		acc = self.new_account("Internet", account("Indirect Expenses")).insert()
		self.assertEqual(acc.name, account("Internet"))
		self.assertEqual(acc.root_type, "Expense")

	def test_parent_must_be_group_of_same_company(self):
		self.assertRaises(frappe.ValidationError, self.new_account("X", account("Cash")).insert)
		make_company("_Test Spend Company 2", "_TS2")
		self.assertRaises(frappe.ValidationError, self.new_account("Y", "Indirect Expenses - _TS2").insert)

	def test_account_type_must_fit_root_type(self):
		acc = self.new_account("Bad Depreciation", account("Current Assets"), account_type="Depreciation")
		self.assertRaises(frappe.ValidationError, acc.insert)

	def test_cannot_post_to_group_account(self):
		self.assertRaises(
			frappe.ValidationError,
			make_journal_entry,
			account("Indirect Expenses"),
			account("Cash"),
			100,
			"2025-03-01",
			account("Main"),
		)

	def test_balance_rolls_up_to_groups(self):
		make_journal_entry(account("Office Rent"), account("Cash"), 500, "2025-03-01", account("Main"))
		make_journal_entry(account("Utilities"), account("Cash"), 200, "2025-03-02", account("Main"))
		self.assertEqual(get_balance(account=account("Office Rent")), 500)
		self.assertEqual(get_balance(account=account("Indirect Expenses")), 700)
		self.assertEqual(get_balance(account=account("Cash")), -700)

	def test_account_with_ledger_entries_cannot_be_deleted_or_grouped(self):
		make_journal_entry(account("Office Rent"), account("Cash"), 500, "2025-03-01", account("Main"))
		self.assertRaises(frappe.ValidationError, frappe.delete_doc, "Account", account("Office Rent"))
		acc = frappe.get_doc("Account", account("Office Rent"))
		acc.is_group = 1
		self.assertRaises(frappe.ValidationError, acc.save)

	def test_standard_chart_is_numbered(self):
		self.assertEqual(frappe.db.get_value("Account", account("Office Rent"), "account_number"), "5203")
		self.assertEqual(frappe.db.get_value("Account", account("Expenses"), "account_number"), "5000")

	def test_account_number_unique_per_company(self):
		with self.assertRaises(frappe.DuplicateEntryError):
			self.new_account("Courier", account("Indirect Expenses"), account_number="5203").insert()
		self.new_account("Courier", account("Indirect Expenses"), account_number="5210").insert()
