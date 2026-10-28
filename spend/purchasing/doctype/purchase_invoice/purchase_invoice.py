# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, nowdate

from spend.spend.accounting import (
	GL_PRECISION,
	get_balance,
	get_company_currency,
	get_fiscal_year,
	make_gl_entries,
	make_reverse_gl_entries,
	validate_ledger_account,
	validate_project,
	get_allowed_accounts,
	is_project_account,
	validate_expense_account,
)
from spend.spend.approval import check_approved
from spend.purchasing.doctype.item.item import get_conversion_factor, update_last_purchase_rate
from spend.purchasing.doctype.item_group.item_group import get_item_group_defaults
from spend.accounts.doctype.journal_entry.journal_entry import validate_cost_center
from spend.spend.expense_category import (
	get_category_account,
	validate_category,
	validate_category_budget,
)
from spend.spend.notifications import notify_budget_usage


class PurchaseInvoice(Document):
	def validate(self):
		self.fiscal_year = get_fiscal_year(self.posting_date)
		self.currency = get_company_currency(self.company)
		self.set_defaults()
		self.validate_supplier()
		self.validate_dates()
		validate_payable_account(self.credit_to, self.company, self.meta.get_label("credit_to"))
		self.validate_items()
		self.set_status()

	def set_defaults(self):
		defaults = frappe.get_cached_value(
			"Company", self.company, ["default_payable_account", "default_cost_center"], as_dict=True
		)
		self.credit_to = self.credit_to or defaults.default_payable_account
		if self.project and not self.cost_center:
			self.cost_center = frappe.db.get_value("Project", self.project, "cost_center")
		self.cost_center = self.cost_center or defaults.default_cost_center
		if not self.credit_to:
			frappe.throw(_("Set Credit To or a Default Payable Account on Company {0}").format(self.company))

	def validate_supplier(self):
		if frappe.db.get_value("Supplier", self.supplier, "disabled"):
			frappe.throw(_("Supplier {0} is disabled").format(frappe.bold(self.supplier)))

	def validate_dates(self):
		if getdate(self.due_date) < getdate(self.posting_date):
			frappe.throw(_("Due Date cannot be before the Posting Date"))
		if self.bill_date and getdate(self.bill_date) > getdate(self.posting_date):
			frappe.throw(_("Supplier Invoice Date cannot be after the Posting Date"))

	def validate_items(self):
		if not self.items:
			frappe.throw(_("Add at least one item"))
		if self.cost_center:
			validate_cost_center(self.cost_center, self.company)
		validate_project(self.project, self.company)

		company = frappe.get_cached_value(
			"Company", self.company, ["default_expense_account", "fixed_asset_account"], as_dict=True
		)
		for item in self.items:
			details = set_item_details(item)
			defaults = get_item_group_defaults(details.item_group, self.company)
			item.project = item.project or self.project
			item.cost_center = item.cost_center or defaults.get("buying_cost_center") or self.cost_center
			if item.is_fixed_asset:
				if item.expense_category or item.expense_sub_category:
					frappe.throw(
						_("Row {0}: a fixed asset item cannot have an expense category").format(item.idx)
					)
				item.expense_account = item.expense_account or company.fixed_asset_account
				missing = _("Set an Asset Account on row {0} or a Fixed Asset Account on Company {1}")
				label, root_types = _("Row {0}: Asset Account").format(item.idx), ("Asset",)
			else:
				validate_category(
					item, item.project, self.company, item.expense_account, _("Row {0}").format(item.idx)
				)
				item.expense_account = item.expense_account or self.get_default_expense_account(
					item,
					[
						get_category_account(item.expense_category, item.expense_sub_category),
						defaults.get("expense_account"),
						company.default_expense_account,
					],
				)
				missing = _("Set an Expense Account on row {0} or a Default Expense Account on Company {1}")
				label, root_types = _("Row {0}: Expense Account").format(item.idx), ("Expense",)
			if not item.expense_account:
				frappe.throw(missing.format(item.idx, self.company))
			validate_ledger_account(item.expense_account, self.company, label, root_types=root_types)
			if not item.cost_center:
				frappe.throw(_("Row {0}: Cost Center is mandatory").format(item.idx))
			validate_cost_center(item.cost_center, self.company, item.idx)
			if item.project != self.project:
				validate_project(item.project, self.company, _("Row {0}: Project").format(item.idx))
			validate_expense_account(
				item.expense_account,
				flt(item.qty) * flt(item.rate),
				item.project,
				item.cost_center,
				self.company,
				self.posting_date,
				_("Row {0}").format(item.idx),
			)
			if flt(item.qty) <= 0:
				frappe.throw(_("Row {0}: Qty must be greater than zero").format(item.idx))
			if flt(item.rate) < 0:
				frappe.throw(_("Row {0}: Rate cannot be negative").format(item.idx))
			validate_whole_number(item.uom, item.qty, _("Row {0}: Qty").format(item.idx))
			item.stock_qty = flt(flt(item.qty) * flt(item.conversion_factor), 6)
			if details.auto_create_assets:
				validate_whole_number(None, item.stock_qty, _("Row {0}: Qty in Default UOM").format(item.idx))
			item.amount = flt(flt(item.qty) * flt(item.rate), GL_PRECISION)

		self.grand_total = flt(sum(item.amount for item in self.items), GL_PRECISION)
		if self.grand_total <= 0:
			frappe.throw(_("Grand Total must be greater than zero"))
		if self.docstatus == 0:
			self.outstanding_amount = self.grand_total

	def get_default_expense_account(self, item, candidates: list) -> str | None:
		"""The first default with budget on the line; the only budgeted account when none has."""
		candidates = [c for c in candidates if c]
		allowed = get_allowed_accounts(self.company, item.project, item.cost_center, self.posting_date)
		budgeted = [c for c in candidates if is_project_account(c, allowed)]
		if budgeted:
			return budgeted[0]
		if len(allowed) == 1:
			return allowed[0]
		return candidates[0] if candidates else None

	def set_status(self):
		self.status = get_status(self)

	def before_submit(self):
		from spend.budgeting.doctype.budget.budget import (
			validate_expense_against_budget,
			validate_project_budget,
		)

		check_approved(self)
		validate_expense_against_budget(
			self, [(item.expense_account, item.cost_center, item.amount) for item in self.items]
		)
		validate_project_budget(
			self, [(item.expense_account, item.project, item.amount) for item in self.items]
		)
		validate_category_budget(
			self,
			[
				(i.expense_account, i.project, i.expense_category, i.expense_sub_category, i.amount)
				for i in self.items
			],
		)

	def on_submit(self):
		make_gl_entries(self.get_gl_map())
		self.update_outstanding()
		update_last_purchase_rate(item.item_code for item in self.items)
		self.make_assets()
		notify_budget_usage(
			self, [(i.expense_account, i.cost_center, i.project, i.amount) for i in self.items]
		)

	def make_assets(self):
		"""One draft Asset per unit of each fixed asset line whose item creates assets."""
		create = {
			code
			for code in {item.item_code for item in self.items if item.is_fixed_asset}
			if frappe.db.get_value("Item", code, "auto_create_assets")
		}
		for item in self.items:
			if item.item_code not in create:
				continue
			units = int(flt(item.stock_qty, 6))
			for _unit in range(units):
				asset = frappe.get_doc(
					{
						"doctype": "Asset",
						"asset_name": item.item_name,
						"item_code": item.item_code,
						"purchase_invoice": self.name,
						"company": self.company,
						"cost_center": item.cost_center,
						"project": item.project,
						"purchase_date": self.bill_date or self.posting_date,
						"available_for_use_date": self.posting_date,
						"gross_purchase_amount": flt(item.amount / units, GL_PRECISION),
						"fixed_asset_account": item.expense_account,
						"calculate_depreciation": 0,
					}
				)
				asset.flags.ignore_permissions = True
				asset.insert()
		if create:
			frappe.msgprint(
				_("Draft assets were created. Complete and submit them under Assets."), alert=True
			)

	def before_cancel(self):
		self.ignore_linked_doctypes = ("GL Entry", "Asset")
		submitted = frappe.get_all("Asset", {"purchase_invoice": self.name, "docstatus": 1}, pluck="name")
		if submitted:
			frappe.throw(_("Cancel the assets of this bill first: {0}").format(", ".join(submitted)))
		payment = get_submitted_payment(self.name)
		if payment:
			frappe.throw(
				_("Cancel Supplier Payment {0} against this bill first").format(frappe.bold(payment))
			)

	def on_cancel(self):
		make_reverse_gl_entries(self.doctype, self.name)
		self.db_set("status", "Cancelled")
		update_last_purchase_rate(item.item_code for item in self.items)
		for asset in frappe.get_all("Asset", {"purchase_invoice": self.name, "docstatus": 0}, pluck="name"):
			frappe.delete_doc("Asset", asset, ignore_permissions=True)

	def get_gl_map(self) -> list[dict]:
		common = {
			"posting_date": self.posting_date,
			"fiscal_year": self.fiscal_year,
			"company": self.company,
			"currency": self.currency,
			"voucher_type": self.doctype,
			"voucher_no": self.name,
			"voucher_subtype": _("Purchase Invoice"),
		}
		remarks = self.remarks or _("Bill {0} from {1}").format(self.bill_no or self.name, self.supplier)
		gl_map = [
			{
				**common,
				"account": item.expense_account,
				"cost_center": item.cost_center,
				"project": item.project,
				"expense_category": item.expense_category,
				"expense_sub_category": item.expense_sub_category,
				"debit": item.amount,
				"credit": 0,
				"voucher_detail_no": item.name,
				"remarks": item.description or item.item_name,
			}
			for item in self.items
			if item.amount
		]
		projects = {item.project for item in self.items}
		gl_map.append(
			{
				**common,
				"account": self.credit_to,
				"project": projects.pop() if len(projects) == 1 else None,
				"debit": 0,
				"credit": self.grand_total,
				"party_type": "Supplier",
				"party": self.supplier,
				"reference_type": self.doctype,
				"reference_name": self.name,
				"remarks": remarks,
			}
		)
		return gl_map

	def update_outstanding(self):
		"""Outstanding is always read back from the payable ledger."""
		self.outstanding_amount = get_invoice_outstanding(self.name, self.credit_to)
		self.db_set({"outstanding_amount": self.outstanding_amount, "status": get_status(self)})


def set_item_details(item) -> frappe._dict:
	"""Name, units and description of a bill line, from its Item."""
	if not item.item_code:
		frappe.throw(_("Row {0}: Item is mandatory").format(item.idx))
	details = frappe.db.get_value(
		"Item",
		item.item_code,
		[
			"item_name",
			"item_group",
			"stock_uom",
			"purchase_uom",
			"description",
			"disabled",
			"is_fixed_asset",
			"auto_create_assets",
		],
		as_dict=True,
	)
	if not details:
		frappe.throw(_("Row {0}: Item {1} does not exist").format(item.idx, frappe.bold(item.item_code)))
	if details.disabled:
		frappe.throw(_("Row {0}: Item {1} is disabled").format(item.idx, frappe.bold(item.item_code)))
	item.item_name = details.item_name
	item.is_fixed_asset = details.is_fixed_asset
	item.stock_uom = details.stock_uom
	item.uom = item.uom or details.purchase_uom or details.stock_uom
	item.conversion_factor = get_conversion_factor(item.item_code, item.uom)
	item.description = item.description or details.description or details.item_name
	return details


def validate_whole_number(uom: str | None, qty: float, label: str):
	"""Units such as Nos cannot be split; any count of assets must be whole too."""
	if uom and not frappe.get_cached_value("UOM", uom, "must_be_whole_number"):
		return
	if flt(qty, 6) != int(flt(qty, 6)):
		frappe.throw(_("{0} must be a whole number").format(label))


def get_status(invoice) -> str:
	if invoice.docstatus == 0:
		return "Draft"
	if invoice.docstatus == 2:
		return "Cancelled"
	outstanding = flt(invoice.outstanding_amount, GL_PRECISION)
	if outstanding <= 0:
		return "Paid"
	if getdate(invoice.due_date) < getdate(nowdate()):
		return "Overdue"
	if outstanding < flt(invoice.grand_total, GL_PRECISION):
		return "Partly Paid"
	return "Unpaid"


def get_invoice_outstanding(invoice: str, credit_to: str) -> float:
	balance = get_balance(account=credit_to, reference_type="Purchase Invoice", reference_name=invoice)
	return flt(-balance, GL_PRECISION)


def get_submitted_payment(invoice: str) -> str | None:
	payment = frappe.qb.DocType("Supplier Payment")
	reference = frappe.qb.DocType("Supplier Payment Reference")
	result = (
		frappe.qb.from_(payment)
		.join(reference)
		.on(reference.parent == payment.name)
		.select(payment.name)
		.where((payment.docstatus == 1) & (reference.purchase_invoice == invoice))
		.limit(1)
		.run(pluck=True)
	)
	return result[0] if result else None


def validate_payable_account(account: str, company: str, label: str):
	validate_ledger_account(account, company, label, root_types=("Liability",))
	if frappe.db.get_value("Account", account, "account_type") != "Payable":
		frappe.throw(_("{0} {1} must be a Payable account").format(label, frappe.bold(account)))


def update_overdue_invoices():
	"""Scheduler entry point: flag unpaid bills whose due date has passed."""
	invoices = frappe.get_all(
		"Purchase Invoice",
		filters={
			"docstatus": 1,
			"status": ("in", ("Unpaid", "Partly Paid")),
			"due_date": ("<", nowdate()),
			"outstanding_amount": (">", 0),
		},
		pluck="name",
	)
	if invoices:
		frappe.db.set_value(
			"Purchase Invoice", {"name": ("in", invoices)}, "status", "Overdue", update_modified=False
		)


@frappe.whitelist()
def make_supplier_payment(source_name: str) -> dict:
	"""New draft Supplier Payment that pays the outstanding amount of this bill."""
	invoice = frappe.get_doc("Purchase Invoice", source_name)
	invoice.check_permission("read")
	if invoice.docstatus != 1 or flt(invoice.outstanding_amount) <= 0:
		frappe.throw(_("Purchase Invoice {0} has nothing outstanding").format(invoice.name))

	payment = frappe.new_doc("Supplier Payment")
	payment.update(
		{
			"supplier": invoice.supplier,
			"company": invoice.company,
			"project": invoice.project,
			"paid_to": invoice.credit_to,
			"paid_from": frappe.get_cached_value("Company", invoice.company, "default_cash_account"),
			"paid_amount": invoice.outstanding_amount,
		}
	)
	payment.append(
		"references",
		{
			"purchase_invoice": invoice.name,
			"due_date": invoice.due_date,
			"grand_total": invoice.grand_total,
			"outstanding_amount": invoice.outstanding_amount,
			"allocated_amount": invoice.outstanding_amount,
		},
	)
	return payment.as_dict()
