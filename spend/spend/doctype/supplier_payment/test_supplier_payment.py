# Copyright (c) 2026, Trojan IT Solutions and Contributors
# See license.txt

import frappe

from spend.spend.accounting import get_balance
from spend.spend.doctype.project.project import get_project_summary
from spend.spend.doctype.supplier_payment.supplier_payment import (
	OverAllocationError,
	ProjectMismatchError,
	get_outstanding_invoices,
)
from spend.tests.utils import (
	TEST_COMPANY,
	SpendTestCase,
	account,
	make_project,
	make_purchase_invoice,
	make_supplier,
	make_supplier_payment,
)

IGNORE_TEST_RECORD_DEPENDENCIES = ["Company", "Account", "Cost Center", "Fiscal Year"]


def status(invoice):
	return frappe.db.get_value("Purchase Invoice", invoice, ["status", "outstanding_amount"])


class IntegrationTestSupplierPayment(SpendTestCase):
	def test_partial_then_full_payment(self):
		invoice = make_purchase_invoice(posting_date="2030-01-01", due_date="2030-12-31")
		make_supplier_payment([(invoice.name, 2000)], posting_date="2030-02-01")
		self.assertEqual(status(invoice.name), ("Partly Paid", 3000))
		make_supplier_payment([(invoice.name, 3000)], posting_date="2030-03-01")
		self.assertEqual(status(invoice.name), ("Paid", 0))
		self.assertEqual(get_balance(account=account("Creditors"), party_type="Supplier"), 0)
		self.assertEqual(get_balance(account=account("Cash")), -5000)

	def test_one_payment_for_several_bills(self):
		first = make_purchase_invoice([("Office Rent", 1000)])
		second = make_purchase_invoice([("Utilities", 400)])
		payment = make_supplier_payment([(first.name, 1000), (second.name, 400)])
		self.assertEqual(payment.total_allocated, 1400)
		self.assertEqual(status(first.name)[0], "Paid")
		self.assertEqual(status(second.name)[0], "Paid")
		self.assertEqual(get_outstanding_invoices("_Test Supplier", TEST_COMPANY), [])

	def test_over_allocation_is_rejected(self):
		invoice = make_purchase_invoice()
		with self.assertRaises(OverAllocationError):
			make_supplier_payment([(invoice.name, 5001)])
		# two drafts that together overpay: the second fails at submit
		first = make_supplier_payment([(invoice.name, 3000)], submit=False)
		second = make_supplier_payment([(invoice.name, 3000)], submit=False)
		first.submit()
		with self.assertRaises(OverAllocationError):
			second.submit()

	def test_allocation_must_match_paid_amount(self):
		invoice = make_purchase_invoice()
		with self.assertRaises(frappe.ValidationError):
			make_supplier_payment([(invoice.name, 1000)], paid_amount=1500)

	def test_rejects_other_supplier_and_non_cash_account(self):
		invoice = make_purchase_invoice()
		make_supplier("_Test Other Supplier")
		with self.assertRaises(frappe.ValidationError):
			make_supplier_payment([(invoice.name, 100)], supplier="_Test Other Supplier")
		with self.assertRaises(frappe.ValidationError):
			make_supplier_payment([(invoice.name, 100)], paid_from=account("Office Rent"))
		draft = make_purchase_invoice(submit=False)
		with self.assertRaises(frappe.ValidationError):
			make_supplier_payment([(draft.name, 100)])

	def test_cancel_restores_outstanding(self):
		invoice = make_purchase_invoice(posting_date="2030-01-01", due_date="2030-12-31")
		payment = make_supplier_payment([(invoice.name, 5000)], posting_date="2030-02-01")
		self.assertEqual(status(invoice.name), ("Paid", 0))
		payment.cancel()
		self.assertEqual(status(invoice.name), ("Unpaid", 5000))
		self.assertEqual(frappe.db.count("GL Entry", {"voucher_no": payment.name}), 4)

	def test_project_fills_in_and_tags_ledger(self):
		project = make_project()
		first = make_purchase_invoice([("Office Rent", 1000)], project=project.name)
		second = make_purchase_invoice([("Utilities", 400)], project=project.name)
		payment = make_supplier_payment([(first.name, 1000), (second.name, 400)])
		self.assertEqual(payment.project, project.name)
		rows = frappe.get_all("GL Entry", {"voucher_no": payment.name}, pluck="project")
		self.assertEqual(set(rows), {project.name})
		summary = get_project_summary(project.name)
		self.assertEqual((summary["billed"], summary["paid"], summary["outstanding"]), (1400, 1400, 0))
		self.assertEqual([p.name for p in summary["payments"]], [payment.name])

	def test_mixed_projects_leave_payment_untagged(self):
		first = make_purchase_invoice(project=make_project("_Test Project A").name)
		second = make_purchase_invoice(project=make_project("_Test Project B").name)
		payment = make_supplier_payment([(first.name, 5000), (second.name, 5000)])
		self.assertFalse(payment.project)

	def test_bill_of_another_project_is_rejected(self):
		project, other = make_project("_Test Project A"), make_project("_Test Project B")
		invoice = make_purchase_invoice(project=other.name)
		with self.assertRaises(ProjectMismatchError):
			make_supplier_payment([(invoice.name, 5000)], project=project.name)
		self.assertEqual(len(get_outstanding_invoices("_Test Supplier", TEST_COMPANY, project.name)), 0)
