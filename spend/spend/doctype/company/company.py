# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from spend.spend.accounting import validate_company_link, validate_ledger_account
from spend.training.sandbox import validate_company as validate_training_company

# (account fieldname on Company, allowed root types)
DEFAULT_ACCOUNT_FIELDS = {
	"default_cash_account": ("Asset",),
	"default_payable_account": ("Liability",),
	"default_expense_account": ("Expense",),
	"fixed_asset_account": ("Asset",),
	"accumulated_depreciation_account": ("Asset",),
	"depreciation_expense_account": ("Expense",),
}


class Company(Document):
	def validate(self):
		self.abbr = (self.abbr or "").strip().upper()
		if not self.abbr:
			frappe.throw(_("Abbreviation is mandatory"))
		if not self.is_new():
			self.validate_default_accounts()
			validate_training_company(self)

	def validate_default_accounts(self):
		for fieldname, root_types in DEFAULT_ACCOUNT_FIELDS.items():
			validate_ledger_account(
				self.get(fieldname), self.name, self.meta.get_label(fieldname), root_types=root_types
			)
		if self.default_cost_center:
			validate_company_link(
				"Cost Center", self.default_cost_center, self.name, _("Default Cost Center")
			)
			if frappe.db.get_value("Cost Center", self.default_cost_center, "is_group"):
				frappe.throw(_("Default Cost Center cannot be a group"))

	def after_insert(self):
		if self.create_default_accounts:
			from spend.spend.setup import create_default_chart

			create_default_chart(self)

	def on_trash(self):
		if frappe.db.exists("GL Entry", {"company": self.name}):
			frappe.throw(_("Cannot delete Company {0} because it has ledger entries").format(self.name))
		for doctype in (
			"Budget",
			"Asset",
			"Journal Entry",
			"Purchase Invoice",
			"Supplier Payment",
			"Project",
			"Recurring Payment",
		):
			if frappe.db.exists(doctype, {"company": self.name}):
				frappe.throw(
					_("Cannot delete Company {0} because {1} records exist").format(self.name, _(doctype))
				)

		# unlink defaults, then remove the trees leaf-first
		for fieldname in (*DEFAULT_ACCOUNT_FIELDS, "default_cost_center"):
			self.db_set(fieldname, None)
		for doctype in ("Account", "Cost Center"):
			frappe.db.delete(doctype, {"company": self.name})


@frappe.whitelist()
def get_company_defaults(company: str) -> dict:
	frappe.has_permission("Company", "read", company, throw=True)
	return frappe.db.get_value(
		"Company",
		company,
		["default_currency", "default_cost_center", *DEFAULT_ACCOUNT_FIELDS],
		as_dict=True,
	)
