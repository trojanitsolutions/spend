# Copyright (c) 2026, Trojan IT Solutions and Contributors
# See license.txt

import frappe

from spend.budgeting.doctype.budget.budget import BudgetExceededError
from spend.budgeting.doctype.budget.test_budget import make_budget
from spend.purchasing.doctype.purchase_invoice import purchase_invoice
from spend.tests.utils import (
	SpendTestCase,
	account,
	make_company,
	make_item,
	make_purchase_invoice,
	make_supplier_payment,
)

IGNORE_TEST_RECORD_DEPENDENCIES = ["Company", "Account", "Cost Center", "Fiscal Year"]


def gl_rows(voucher_no, **filters):
	return frappe.get_all(
		"GL Entry",
		filters={"voucher_no": voucher_no, **filters},
		fields=["account", "cost_center", "debit", "credit", "party", "reference_name", "is_cancelled"],
		order_by="creation",
	)


def make_bill(lines):
	"""Draft bill with raw item rows, so the controller fills them in."""
	bill = make_purchase_invoice(submit=False)
	bill.set("items", lines)
	return bill.save()


class IntegrationTestPurchaseInvoice(SpendTestCase):
	def test_submit_posts_expense_and_payable(self):
		invoice = make_purchase_invoice([("Office Rent", 5000), ("Utilities", 1200.5)])
		self.assertEqual(invoice.grand_total, 6200.5)
		self.assertEqual(invoice.outstanding_amount, 6200.5)
		self.assertEqual(invoice.status, "Overdue")  # due 2025-03-31, already past
		self.assertEqual(invoice.credit_to, account("Creditors"))

		rows = gl_rows(invoice.name)
		debits = {r.account: r for r in rows if r.debit}
		self.assertEqual(debits[account("Office Rent")].debit, 5000)
		self.assertEqual(debits[account("Office Rent")].cost_center, account("Main"))
		credit = next(r for r in rows if r.credit)
		self.assertEqual(credit.account, account("Creditors"))
		self.assertEqual(credit.credit, 6200.5)
		self.assertEqual(credit.party, "_Test Supplier")
		self.assertEqual(credit.reference_name, invoice.name)

	def test_item_fills_the_line(self):
		from spend.projects.doctype.expense_category.test_expense_category import make_category

		item = make_item("_Test Cement", item_name="Cement 50 kg", stock_uom="Bag", description="OPC 53")
		rent = make_category("_Test Rent Category", expense_account="Office Rent")
		line = {"item_code": item.name, "qty": 2, "rate": 400}
		invoice = make_bill(
			[
				line,
				{**line, "expense_account": account("Utilities"), "description": "Own text"},
				{**line, "expense_category": rent.name},
			]
		)
		default, own, category = invoice.items
		self.assertEqual(default.expense_account, account("Miscellaneous Expenses"))
		self.assertEqual(
			(default.item_name, default.uom, default.description), ("Cement 50 kg", "Bag", "OPC 53")
		)
		self.assertEqual(default.amount, 800)
		self.assertEqual((own.expense_account, own.description), (account("Utilities"), "Own text"))
		self.assertEqual(category.expense_account, account("Office Rent"))

	def test_item_is_required_and_enabled(self):
		item = make_item("_Test Old Item", disabled=1)
		for line in ({"qty": 1, "rate": 10}, {"item_code": item.name, "qty": 1, "rate": 10}):
			self.assertRaises(frappe.ValidationError, make_bill, [line])

	def test_status_unpaid_when_not_due(self):
		invoice = make_purchase_invoice(posting_date="2030-01-01", due_date="2030-12-31")
		self.assertEqual(invoice.status, "Unpaid")

	def test_expense_lines_must_be_expense_ledgers_of_company(self):
		with self.assertRaises(frappe.ValidationError):
			make_purchase_invoice([("Cash", 100)])
		other = make_company("_Test Other Company", "_TOC")
		with self.assertRaises(frappe.ValidationError):
			make_purchase_invoice(
				items=None, company=other.name
			)  # Office Rent - _TSC belongs to another company

	def test_validations(self):
		with self.assertRaises(frappe.ValidationError):
			make_purchase_invoice(due_date="2025-02-01")
		with self.assertRaises(frappe.ValidationError):
			make_purchase_invoice([("Office Rent", 0)])
		with self.assertRaises(frappe.ValidationError):
			make_purchase_invoice(credit_to=account("Cash"))

	def test_stop_budget_blocks_bill(self):
		make_budget({account("Office Rent"): 3000}, action="Stop")
		with self.assertRaises(BudgetExceededError):
			make_purchase_invoice([("Office Rent", 5000)])
		make_purchase_invoice([("Office Rent", 3000)])

	def test_cancel_reverses_and_keeps_history(self):
		invoice = make_purchase_invoice()
		invoice.cancel()
		self.assertEqual(frappe.db.get_value("Purchase Invoice", invoice.name, "status"), "Cancelled")
		rows = gl_rows(invoice.name)
		self.assertEqual(len(rows), 4)  # 2 originals + 2 reversals, all flagged
		self.assertTrue(all(r.is_cancelled for r in rows))

	def test_cannot_cancel_paid_bill(self):
		invoice = make_purchase_invoice()
		payment = make_supplier_payment([(invoice.name, 1000)])
		invoice.reload()
		with self.assertRaises(frappe.ValidationError):
			invoice.cancel()
		payment.cancel()
		invoice.reload()
		invoice.cancel()

	def test_overdue_job(self):
		invoice = make_purchase_invoice(posting_date="2030-01-01", due_date="2030-01-31")
		frappe.db.set_value("Purchase Invoice", invoice.name, "due_date", "2025-01-31")
		purchase_invoice.update_overdue_invoices()
		self.assertEqual(frappe.db.get_value("Purchase Invoice", invoice.name, "status"), "Overdue")

	def test_make_payment_maps_outstanding(self):
		invoice = make_purchase_invoice()
		payment = purchase_invoice.make_supplier_payment(invoice.name)
		self.assertEqual(payment["paid_amount"], 5000)
		self.assertEqual(payment["references"][0]["purchase_invoice"], invoice.name)
		self.assertEqual(payment["paid_from"], account("Cash"))
