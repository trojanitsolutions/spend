# Copyright (c) 2026, Trojan IT Solutions and Contributors
# See license.txt

import frappe

from spend.purchasing.doctype.supplier.supplier import get_supplier_outstanding
from spend.tests.utils import SpendTestCase, make_purchase_invoice, make_supplier

IGNORE_TEST_RECORD_DEPENDENCIES = ["Company", "Account", "Cost Center", "Fiscal Year"]


class IntegrationTestSupplier(SpendTestCase):
	def test_supplier_is_named_by_supplier_name(self):
		supplier = make_supplier("  _Test Stationers  ")
		self.assertEqual(supplier.name, "_Test Stationers")

	def test_outstanding_comes_from_party_ledger(self):
		make_purchase_invoice([("Office Rent", 4000)])
		make_purchase_invoice([("Utilities", 1500)])
		self.assertEqual(get_supplier_outstanding("_Test Supplier"), 5500)

	def test_cannot_delete_supplier_with_bills(self):
		make_purchase_invoice()
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("Supplier", "_Test Supplier")

	def test_disabled_supplier_cannot_be_billed(self):
		make_supplier("_Test Old Supplier", disabled=1)
		with self.assertRaises(frappe.ValidationError):
			make_purchase_invoice(supplier="_Test Old Supplier")
