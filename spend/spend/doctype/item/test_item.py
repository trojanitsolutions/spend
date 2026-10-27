# Copyright (c) 2026, Trojan IT Solutions and Contributors
# See license.txt

import frappe

from spend.spend.doctype.item.item import get_item_details
from spend.spend.doctype.purchase_invoice.test_purchase_invoice import make_bill
from spend.tests.utils import (
	TEST_COMPANY,
	SpendTestCase,
	account,
	make_item,
	make_purchase_invoice,
	make_supplier,
)

IGNORE_TEST_RECORD_DEPENDENCIES = ["Company", "Account", "Cost Center", "Fiscal Year"]


def make_item_group(name, parent="All Item Groups", is_group=0, **defaults):
	return frappe.get_doc(
		{
			"doctype": "Item Group",
			"item_group_name": name,
			"parent_item_group": parent,
			"is_group": is_group,
			"item_group_defaults": [{"company": TEST_COMPANY, **defaults}] if defaults else [],
		}
	).insert()


class IntegrationTestItem(SpendTestCase):
	def test_uoms(self):
		item = make_item("_Test Cement Bag", stock_uom="Kg", uoms=[{"uom": "Bag", "conversion_factor": 50}])
		self.assertEqual({(r.uom, r.conversion_factor) for r in item.uoms}, {("Kg", 1), ("Bag", 50)})

		item.purchase_uom = "Tonne"
		self.assertRaisesRegex(frappe.ValidationError, "Add .* to the UOMs table", item.save)
		item.reload()
		item.append("uoms", {"uom": "Bag", "conversion_factor": 25})
		self.assertRaisesRegex(frappe.ValidationError, "repeated", item.save)

	def test_bill_line_converts_to_stock_uom(self):
		item = make_item(
			"_Test Cement Bag",
			stock_uom="Kg",
			purchase_uom="Bag",
			uoms=[{"uom": "Bag", "conversion_factor": 50}],
		)
		bill = make_bill([{"item_code": item.name, "qty": 3, "rate": 400}])
		line = bill.items[0]
		self.assertEqual(
			(line.uom, line.conversion_factor, line.stock_qty, line.stock_uom), ("Bag", 50, 150, "Kg")
		)
		self.assertRaisesRegex(
			frappe.ValidationError,
			"whole number",
			make_bill,
			[{"item_code": item.name, "qty": 1.5, "rate": 400}],
		)

	def test_item_group_defaults(self):
		parent = make_item_group(
			"_Test Materials",
			is_group=1,
			expense_account=account("Utilities"),
			buying_cost_center=account("Main"),
		)
		child = make_item_group("_Test Cement", parent=parent.name)
		item = make_item("_Test Grouped Item", item_group=child.name)
		line = make_bill([{"item_code": item.name, "qty": 1, "rate": 10}]).items[0]
		self.assertEqual(line.expense_account, account("Utilities"))  # from the parent group

		self.assertRaisesRegex(
			frappe.ValidationError, "must be a group", make_item_group, "_Test Under Leaf", parent=child.name
		)
		self.assertRaises(
			frappe.ValidationError, make_item_group, "_Test Bad", expense_account=account("Cash")
		)

	def test_buying_rate(self):
		item = make_item("_Test Rated Item", standard_rate=90, uoms=[{"uom": "Box", "conversion_factor": 10}])
		details = get_item_details(item.name, TEST_COMPANY, uom="Box")
		self.assertEqual((details["rate"], details["conversion_factor"]), (900, 10))

		bill = make_purchase_invoice(submit=False)
		bill.set("items", [{"item_code": item.name, "uom": "Box", "qty": 1, "rate": 1000}])
		bill.save().submit()
		self.assertEqual(frappe.db.get_value("Item", item.name, "last_purchase_rate"), 100)
		self.assertEqual(get_item_details(item.name, TEST_COMPANY, make_supplier().name, "Box")["rate"], 1000)

		bill.cancel()
		self.assertEqual(frappe.db.get_value("Item", item.name, "last_purchase_rate"), 0)

	def test_fixed_asset_item(self):
		item = make_item("_Test Laptop", is_fixed_asset=1, auto_create_assets=1)
		bill = make_purchase_invoice(submit=False)
		bill.set("items", [{"item_code": item.name, "qty": 2, "rate": 50000}])
		bill.save()
		self.assertEqual(bill.items[0].expense_account, account("Office Equipment"))
		bill.submit()

		debit = frappe.get_all("GL Entry", {"voucher_no": bill.name, "debit": (">", 0)}, ["account", "debit"])
		self.assertEqual([(d.account, d.debit) for d in debit], [(account("Office Equipment"), 100000)])
		assets = frappe.get_all(
			"Asset", {"purchase_invoice": bill.name}, ["gross_purchase_amount", "docstatus", "item_code"]
		)
		self.assertEqual(len(assets), 2)
		self.assertTrue(all(a.gross_purchase_amount == 50000 and a.docstatus == 0 for a in assets))

		bill.cancel()
		self.assertFalse(frappe.db.exists("Asset", {"purchase_invoice": bill.name}))

		from spend.spend.doctype.expense_category.test_expense_category import make_category

		category = make_category("_Test Asset Category", expense_account="Utilities")
		self.assertRaisesRegex(
			frappe.ValidationError,
			"expense category",
			make_bill,
			[{"item_code": item.name, "qty": 1, "rate": 1, "expense_category": category.name}],
		)
