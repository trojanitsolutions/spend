# Copyright (c) 2026, Trojan IT Solutions and Contributors
# See license.txt

import frappe

from spend.tests.utils import (
	TEST_ABBR,
	SpendTestCase,
	account,
	make_company,
	make_journal_entry,
	setup_test_data,
)

IGNORE_TEST_RECORD_DEPENDENCIES = ["Currency", "Country", "Fiscal Year", "Account", "Cost Center"]


class IntegrationTestCompany(SpendTestCase):
	def test_default_chart_and_defaults_created(self):
		self.assertEqual(self.company.reload().default_cost_center, f"Main - {TEST_ABBR}")
		self.assertEqual(self.company.depreciation_expense_account, account("Depreciation"))
		self.assertEqual(self.company.accumulated_depreciation_account, account("Accumulated Depreciation"))
		roots = frappe.get_all(
			"Account",
			filters={"company": self.company.name, "parent_account": ("is", "not set")},
			pluck="root_type",
		)
		self.assertCountEqual(roots, ["Asset", "Liability", "Equity", "Income", "Expense"])

	def test_child_accounts_inherit_root_type(self):
		self.assertEqual(frappe.db.get_value("Account", account("Depreciation"), "root_type"), "Expense")
		self.assertEqual(
			frappe.db.get_value("Account", account("Depreciation"), "report_type"), "Profit and Loss"
		)
		self.assertEqual(frappe.db.get_value("Account", account("Creditors"), "root_type"), "Liability")

	def test_default_account_must_match_root_type(self):
		self.company.depreciation_expense_account = account("Creditors")
		self.assertRaises(frappe.ValidationError, self.company.save)

	def test_company_with_ledger_entries_cannot_be_deleted(self):
		make_journal_entry(account("Office Rent"), account("Cash"), 100, "2025-03-01", account("Main"))
		self.assertRaises(frappe.ValidationError, frappe.delete_doc, "Company", self.company.name)

	def test_second_company_gets_its_own_chart(self):
		other = make_company("_Test Spend Company 2", "_TS2")
		self.assertTrue(frappe.db.exists("Account", "Cash - _TS2"))
		self.assertEqual(frappe.db.get_value("Company", other.name, "default_cash_account"), "Cash - _TS2")
