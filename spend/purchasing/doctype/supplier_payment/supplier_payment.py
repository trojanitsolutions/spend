# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from spend.spend.accounting import (
	GL_PRECISION,
	get_company_currency,
	get_fiscal_year,
	make_gl_entries,
	make_reverse_gl_entries,
	validate_company_link,
	validate_ledger_account,
)
from spend.spend.approval import check_approved
from spend.purchasing.doctype.purchase_invoice.purchase_invoice import (
	get_invoice_outstanding,
	validate_payable_account,
)


class OverAllocationError(frappe.ValidationError):
	pass


class ProjectMismatchError(frappe.ValidationError):
	pass


class SupplierPayment(Document):
	def validate(self):
		self.fiscal_year = get_fiscal_year(self.posting_date)
		self.currency = get_company_currency(self.company)
		self.paid_to = self.paid_to or frappe.get_cached_value(
			"Company", self.company, "default_payable_account"
		)
		self.validate_accounts()
		self.validate_references()
		self.set_project()

	def validate_accounts(self):
		label = self.meta.get_label("paid_from")
		validate_ledger_account(self.paid_from, self.company, label, root_types=("Asset",))
		if frappe.db.get_value("Account", self.paid_from, "account_type") not in ("Cash", "Bank"):
			frappe.throw(
				_("{0} {1} must be a Cash or Bank account").format(label, frappe.bold(self.paid_from))
			)
		validate_payable_account(self.paid_to, self.company, self.meta.get_label("paid_to"))
		if flt(self.paid_amount, GL_PRECISION) <= 0:
			frappe.throw(_("Paid Amount must be greater than zero"))

	def validate_references(self):
		if not self.references:
			frappe.throw(_("Add at least one bill to pay"))

		seen = set()
		for row in self.references:
			if row.purchase_invoice in seen:
				frappe.throw(_("Row {0}: Bill {1} is listed twice").format(row.idx, row.purchase_invoice))
			seen.add(row.purchase_invoice)

			invoice = frappe.db.get_value(
				"Purchase Invoice",
				row.purchase_invoice,
				[
					"docstatus",
					"supplier",
					"company",
					"credit_to",
					"due_date",
					"grand_total",
					"outstanding_amount",
					"project",
				],
				as_dict=True,
			)
			if not invoice or invoice.docstatus != 1:
				frappe.throw(_("Row {0}: Bill {1} is not submitted").format(row.idx, row.purchase_invoice))
			if invoice.supplier != self.supplier or invoice.company != self.company:
				frappe.throw(
					_("Row {0}: Bill {1} belongs to another supplier or company").format(
						row.idx, frappe.bold(row.purchase_invoice)
					)
				)
			if invoice.credit_to != self.paid_to:
				frappe.throw(
					_("Row {0}: Bill {1} is payable on {2}, not {3}").format(
						row.idx, row.purchase_invoice, invoice.credit_to, self.paid_to
					)
				)

			if self.project and invoice.project != self.project:
				frappe.throw(
					_("Row {0}: Bill {1} is not for Project {2}").format(
						row.idx, frappe.bold(row.purchase_invoice), frappe.bold(self.project)
					),
					ProjectMismatchError,
				)

			row.due_date, row.grand_total = invoice.due_date, invoice.grand_total
			if self.docstatus == 0:
				row.outstanding_amount = invoice.outstanding_amount
			row.allocated_amount = flt(row.allocated_amount, GL_PRECISION)
			if row.allocated_amount <= 0:
				frappe.throw(_("Row {0}: Allocated amount must be greater than zero").format(row.idx))
			if self.docstatus == 0:
				validate_allocation(row, row.outstanding_amount)

		self.total_allocated = flt(sum(row.allocated_amount for row in self.references), GL_PRECISION)
		if abs(self.total_allocated - flt(self.paid_amount, GL_PRECISION)) >= 0.01:
			frappe.throw(
				_("Total allocated ({0}) must equal the Paid Amount ({1})").format(
					self.total_allocated, flt(self.paid_amount, GL_PRECISION)
				)
			)

	def set_project(self):
		"""Tag the payment with the bills' project when they all share one."""
		if not self.project:
			projects = set(
				frappe.get_all(
					"Purchase Invoice",
					filters={"name": ("in", [row.purchase_invoice for row in self.references])},
					pluck="project",
				)
			)
			if len(projects) == 1:
				self.project = projects.pop()
		# bills of a completed project can still be paid, so only the company is checked
		validate_company_link("Project", self.project, self.company)

	def before_submit(self):
		check_approved(self)
		# lock the bills and re-check against the ledger so two payments cannot overpay one bill
		for row in self.references:
			frappe.db.get_value("Purchase Invoice", row.purchase_invoice, "name", for_update=True)
			validate_allocation(row, get_invoice_outstanding(row.purchase_invoice, self.paid_to))

	def on_submit(self):
		make_gl_entries(self.get_gl_map())
		self.update_invoices()

	def before_cancel(self):
		self.ignore_linked_doctypes = ("GL Entry", "Purchase Invoice")

	def on_cancel(self):
		make_reverse_gl_entries(self.doctype, self.name)
		self.update_invoices()

	def update_invoices(self):
		for row in self.references:
			frappe.get_doc("Purchase Invoice", row.purchase_invoice).update_outstanding()

	def get_gl_map(self) -> list[dict]:
		common = {
			"posting_date": self.posting_date,
			"fiscal_year": self.fiscal_year,
			"company": self.company,
			"currency": self.currency,
			"voucher_type": self.doctype,
			"voucher_no": self.name,
			"voucher_subtype": _("Supplier Payment"),
			"project": self.project,
		}
		remarks = self.remarks or _("Payment to {0}").format(self.supplier)
		gl_map = [
			{
				**common,
				"account": self.paid_to,
				"debit": row.allocated_amount,
				"credit": 0,
				"party_type": "Supplier",
				"party": self.supplier,
				"reference_type": "Purchase Invoice",
				"reference_name": row.purchase_invoice,
				"voucher_detail_no": row.name,
				"remarks": remarks,
			}
			for row in self.references
		]
		gl_map.append(
			{
				**common,
				"account": self.paid_from,
				"debit": 0,
				"credit": self.total_allocated,
				"remarks": remarks,
			}
		)
		return gl_map


def validate_allocation(row, outstanding: float):
	if row.allocated_amount - flt(outstanding, GL_PRECISION) >= 0.01:
		frappe.throw(
			_("Row {0}: Allocated amount {1} is more than the outstanding {2} of bill {3}").format(
				row.idx,
				row.allocated_amount,
				flt(outstanding, GL_PRECISION),
				frappe.bold(row.purchase_invoice),
			),
			OverAllocationError,
		)


@frappe.whitelist()
def get_outstanding_invoices(supplier: str, company: str, project: str | None = None) -> list[dict]:
	"""Submitted bills of a supplier with an amount still owed, oldest due first."""
	frappe.has_permission("Purchase Invoice", "read", throw=True)
	filters = {"supplier": supplier, "company": company, "docstatus": 1, "outstanding_amount": (">", 0)}
	if project:
		filters["project"] = project
	return frappe.get_list(
		"Purchase Invoice",
		filters=filters,
		fields=[
			"name",
			"posting_date",
			"due_date",
			"bill_no",
			"grand_total",
			"outstanding_amount",
			"credit_to",
			"project",
		],
		order_by="due_date asc, posting_date asc",
	)
