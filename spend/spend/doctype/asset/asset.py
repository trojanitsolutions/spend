# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from spend.spend.accounting import GL_PRECISION, validate_ledger_account
from spend.spend.depreciation import (
	calculate_schedule,
	get_default_start_date,
	get_number_of_depreciations,
	update_asset_values,
)
from spend.spend.doctype.journal_entry.journal_entry import validate_cost_center

COMPANY_DEFAULTS = {
	"fixed_asset_account": "fixed_asset_account",
	"accumulated_depreciation_account": "accumulated_depreciation_account",
	"depreciation_expense_account": "depreciation_expense_account",
	"cost_center": "default_cost_center",
}


class Asset(Document):
	def validate(self):
		self.set_company_defaults()
		self.validate_amounts_and_dates()
		self.validate_accounts()
		if self.calculate_depreciation:
			self.set_depreciation_parameters()
		else:
			self.total_number_of_depreciations = 0
		if self.docstatus == 0:
			self.status = "Draft"
			self.accumulated_depreciation = 0
			self.value_after_depreciation = self.gross_purchase_amount

	def set_company_defaults(self):
		defaults = frappe.db.get_value("Company", self.company, list(COMPANY_DEFAULTS.values()), as_dict=True)
		for field, company_field in COMPANY_DEFAULTS.items():
			if not self.get(field):
				self.set(field, defaults.get(company_field))

	def validate_amounts_and_dates(self):
		if flt(self.gross_purchase_amount) <= 0:
			frappe.throw(_("Gross Purchase Amount must be greater than zero"))
		if getdate(self.available_for_use_date) < getdate(self.purchase_date):
			frappe.throw(_("Capitalization Date cannot be before Purchase Date"))
		if self.calculate_depreciation:
			if flt(self.salvage_value) < 0 or flt(self.salvage_value) >= flt(self.gross_purchase_amount):
				frappe.throw(_("Salvage Value must be zero or more and less than the Gross Purchase Amount"))
			if flt(self.useful_life_years) <= 0:
				frappe.throw(_("Useful Life must be greater than zero"))

	def validate_accounts(self):
		validate_ledger_account(self.fixed_asset_account, self.company, _("Fixed Asset Account"), ("Asset",))
		if self.calculate_depreciation:
			if not (self.accumulated_depreciation_account and self.depreciation_expense_account):
				frappe.throw(_("Set the depreciation accounts on the asset or the company"))
			validate_ledger_account(
				self.accumulated_depreciation_account,
				self.company,
				_("Accumulated Depreciation Account"),
				("Asset",),
			)
			validate_ledger_account(
				self.depreciation_expense_account,
				self.company,
				_("Depreciation Expense Account"),
				("Expense",),
			)
			if self.accumulated_depreciation_account == self.fixed_asset_account:
				frappe.throw(_("Accumulated Depreciation Account must differ from the Fixed Asset Account"))
		if self.capitalization_credit_account and self.purchase_invoice:
			frappe.throw(
				_(
					"Purchase Invoice {0} already booked this asset. Clear the Capitalization Credit Account."
				).format(self.purchase_invoice)
			)
		if self.capitalization_credit_account:
			validate_ledger_account(
				self.capitalization_credit_account,
				self.company,
				_("Capitalization Credit Account"),
				("Asset", "Liability", "Equity"),
			)
		if self.cost_center:
			validate_cost_center(self.cost_center, self.company)

	def set_depreciation_parameters(self):
		self.total_number_of_depreciations = get_number_of_depreciations(
			self.useful_life_years, self.frequency_of_depreciation
		)
		if not self.depreciation_start_date:
			self.depreciation_start_date = get_default_start_date(
				self.available_for_use_date, self.frequency_of_depreciation
			)
		if getdate(self.depreciation_start_date) < getdate(self.available_for_use_date):
			frappe.throw(_("Depreciation Start Date cannot be before the Capitalization Date"))
		# raises on inconsistent inputs (e.g. WDV without rate and salvage)
		calculate_schedule(
			cost=self.gross_purchase_amount,
			salvage=self.salvage_value,
			method=self.depreciation_method,
			frequency=self.frequency_of_depreciation,
			number_of_depreciations=1,
			start_date=self.depreciation_start_date,
			annual_rate=self.rate_of_depreciation,
		)

	def on_update(self):
		if self.docstatus == 0:
			self.sync_draft_schedule()

	def sync_draft_schedule(self):
		"""Keep exactly one draft schedule in step with the draft asset."""
		existing = frappe.db.get_value("Asset Depreciation Schedule", {"asset": self.name, "docstatus": 0})
		if not self.calculate_depreciation:
			if existing:
				frappe.delete_doc("Asset Depreciation Schedule", existing, ignore_permissions=True)
			self.db_set("depreciation_schedule", None)
			return

		schedule = (
			frappe.get_doc("Asset Depreciation Schedule", existing)
			if existing
			else frappe.new_doc("Asset Depreciation Schedule")
		)
		schedule.set_from_asset(self)
		schedule.flags.ignore_permissions = True
		schedule.save()
		self.db_set("depreciation_schedule", schedule.name)

	def before_submit(self):
		if self.calculate_depreciation and not self.depreciation_schedule:
			self.sync_draft_schedule()

	def on_submit(self):
		if self.capitalization_credit_account:
			self.db_set("capitalization_entry", self.make_capitalization_entry())
		if self.calculate_depreciation:
			schedule = frappe.get_doc("Asset Depreciation Schedule", self.depreciation_schedule)
			schedule.set_from_asset(self)  # submitted values are authoritative
			schedule.flags.ignore_permissions = True
			schedule.submit()
		self.db_set("status", "Submitted")
		update_asset_values(self.name)

	def make_capitalization_entry(self) -> str:
		je = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"voucher_type": "Asset Capitalization",
				"company": self.company,
				"posting_date": self.available_for_use_date,
				"title": _("Capitalization: {0}").format(self.asset_name),
				"user_remark": _("Capitalization of {0} ({1})").format(self.asset_name, self.name),
				"asset": self.name,
				"accounts": [
					{
						"account": self.fixed_asset_account,
						"debit": self.gross_purchase_amount,
						"reference_type": "Asset",
						"reference_name": self.name,
					},
					{
						"account": self.capitalization_credit_account,
						"credit": self.gross_purchase_amount,
						"reference_type": "Asset",
						"reference_name": self.name,
					},
				],
			}
		)
		je.flags.ignore_permissions = True
		je.insert()
		je.submit()
		return je.name

	def before_cancel(self):
		self.ignore_linked_doctypes = ("Asset Depreciation Schedule", "Journal Entry", "GL Entry")
		posted = frappe.get_all(
			"Journal Entry",
			filters={"asset": self.name, "voucher_type": "Depreciation Entry", "docstatus": 1},
			pluck="name",
		)
		if posted:
			frappe.throw(
				_("Cancel the posted depreciation entries of this asset first: {0}").format(", ".join(posted))
			)

	def on_cancel(self):
		if self.depreciation_schedule:
			schedule = frappe.get_doc("Asset Depreciation Schedule", self.depreciation_schedule)
			if schedule.docstatus == 1:
				schedule.flags.ignore_permissions = True
				schedule.cancel()
		if self.capitalization_entry:
			je = frappe.get_doc("Journal Entry", self.capitalization_entry)
			if je.docstatus == 1:
				je.flags.ignore_permissions = True
				je.flags.from_asset = True
				je.cancel()
		self.db_set("status", "Cancelled")

	def on_trash(self):
		for schedule in frappe.get_all(
			"Asset Depreciation Schedule", filters={"asset": self.name, "docstatus": 0}, pluck="name"
		):
			frappe.delete_doc("Asset Depreciation Schedule", schedule, ignore_permissions=True)


@frappe.whitelist()
def get_schedule_preview(asset: str) -> list[dict]:
	doc = frappe.get_doc("Asset", asset)
	doc.check_permission("read")
	if not doc.depreciation_schedule:
		return []
	return frappe.get_all(
		"Depreciation Schedule",
		filters={"parent": doc.depreciation_schedule},
		fields=[
			"schedule_date",
			"opening_book_value",
			"depreciation_amount",
			"accumulated_depreciation_amount",
			"closing_book_value",
			"journal_entry",
		],
		order_by="idx",
	)
