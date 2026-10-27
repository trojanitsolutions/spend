# Copyright (c) 2026, Trojan IT Solutions and Contributors
# See license.txt

import frappe

from spend.spend.accounting import FiscalYearError, get_balance
from spend.tests.utils import TEST_COMPANY, SpendTestCase, account, make_journal_entry, setup_test_data

IGNORE_TEST_RECORD_DEPENDENCIES = ["Company", "Account", "Cost Center", "Asset"]


class IntegrationTestJournalEntry(SpendTestCase):
	def test_submit_creates_balanced_gl(self):
		je = make_journal_entry(account("Office Rent"), account("Cash"), 1500, "2025-05-10", account("Main"))
		gl = frappe.get_all(
			"GL Entry",
			filters={"voucher_no": je.name},
			fields=["account", "debit", "credit", "cost_center", "fiscal_year"],
		)
		self.assertEqual(len(gl), 2)
		self.assertEqual(sum(g.debit for g in gl), sum(g.credit for g in gl))
		self.assertEqual(gl[0].fiscal_year, je.fiscal_year)

	def test_cost_center_defaults_for_expense(self):
		je = make_journal_entry(account("Office Rent"), account("Cash"), 100, "2025-05-10")
		self.assertEqual(je.accounts[0].cost_center, account("Main"))
		self.assertFalse(je.accounts[1].cost_center)

	def test_unbalanced_entry_rejected(self):
		je = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"company": TEST_COMPANY,
				"posting_date": "2025-05-10",
				"accounts": [
					{"account": account("Office Rent"), "debit": 100},
					{"account": account("Cash"), "credit": 90},
				],
			}
		)
		self.assertRaises(frappe.ValidationError, je.insert)

	def test_row_with_debit_and_credit_rejected(self):
		je = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"company": TEST_COMPANY,
				"posting_date": "2025-05-10",
				"accounts": [
					{"account": account("Office Rent"), "debit": 100, "credit": 100},
					{"account": account("Cash"), "credit": 0},
				],
			}
		)
		self.assertRaises(frappe.ValidationError, je.insert)

	def test_posting_outside_fiscal_year_rejected(self):
		self.assertRaises(
			FiscalYearError, make_journal_entry, account("Office Rent"), account("Cash"), 1, "1999-01-01"
		)

	def test_cancel_reverses_without_deleting(self):
		je = make_journal_entry(account("Office Rent"), account("Cash"), 400, "2025-05-10", account("Main"))
		je.cancel()
		rows = frappe.get_all(
			"GL Entry", filters={"voucher_no": je.name}, fields=["debit", "credit", "is_cancelled"]
		)
		self.assertEqual(len(rows), 4)
		self.assertTrue(all(r.is_cancelled for r in rows))
		self.assertEqual(get_balance(account=account("Office Rent")), 0)

	def test_gl_entry_is_immutable(self):
		je = make_journal_entry(account("Office Rent"), account("Cash"), 400, "2025-05-10", account("Main"))
		gle = frappe.get_doc("GL Entry", {"voucher_no": je.name, "debit": 400})
		gle.debit = 1
		self.assertRaises(frappe.ValidationError, gle.save)
		self.assertRaises(frappe.ValidationError, gle.delete)

	def test_manual_depreciation_entry_rejected(self):
		self.assertRaises(
			frappe.ValidationError,
			make_journal_entry,
			account("Depreciation"),
			account("Accumulated Depreciation"),
			10,
			"2025-05-10",
			voucher_type="Depreciation Entry",
		)
