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
	validate_project,
)
from spend.spend.approval import check_approved
from spend.spend.expense_category import validate_category, validate_category_budget
from spend.spend.notifications import notify_budget_usage


class JournalEntry(Document):
	def validate(self):
		self.fiscal_year = get_fiscal_year(self.posting_date)
		self.currency = get_company_currency(self.company)
		self.validate_rows()
		self.set_totals()
		self.validate_depreciation_reference()
		self.validate_recurring_reference()
		if not self.title:
			self.title = self.user_remark or self.voucher_type

	def validate_rows(self):
		if not self.accounts:
			frappe.throw(_("Add at least one debit and one credit row"))

		default_cost_center = frappe.get_cached_value("Company", self.company, "default_cost_center")
		for row in self.accounts:
			row.currency = self.currency
			row.debit, row.credit = flt(row.debit, GL_PRECISION), flt(row.credit, GL_PRECISION)
			if row.debit < 0 or row.credit < 0:
				frappe.throw(_("Row {0}: Debit and Credit cannot be negative").format(row.idx))
			if bool(row.debit) == bool(row.credit):
				frappe.throw(_("Row {0}: Enter either a debit or a credit amount").format(row.idx))

			validate_ledger_account(row.account, self.company, _("Row {0}: Account").format(row.idx))

			report_type = frappe.db.get_value("Account", row.account, "report_type")
			if report_type == "Profit and Loss" and not row.cost_center:
				row.cost_center = default_cost_center
				if not row.cost_center:
					frappe.throw(
						_("Row {0}: Cost Center is mandatory for income and expense accounts").format(row.idx)
					)
			if row.cost_center:
				validate_cost_center(row.cost_center, self.company, row.idx)
			validate_party(row)
			validate_project(row.project, self.company, _("Row {0}: Project").format(row.idx))
			validate_category(row, row.project, self.company, row.account, _("Row {0}").format(row.idx))

		if not any(r.debit for r in self.accounts) or not any(r.credit for r in self.accounts):
			frappe.throw(_("A Journal Entry needs at least one debit and one credit row"))

	def set_totals(self):
		self.total_debit = flt(sum(r.debit for r in self.accounts), GL_PRECISION)
		self.total_credit = flt(sum(r.credit for r in self.accounts), GL_PRECISION)
		if abs(self.total_debit - self.total_credit) >= 0.01:
			frappe.throw(
				_("Total Debit ({0}) must equal Total Credit ({1})").format(
					self.total_debit, self.total_credit
				)
			)

	def validate_depreciation_reference(self):
		if self.voucher_type == "Asset Capitalization" and not self.asset:
			frappe.throw(_("Asset Capitalization entries are created by submitting an Asset"))
		if self.voucher_type != "Depreciation Entry":
			if self.depreciation_schedule_row:
				frappe.throw(_("Only Depreciation Entries can reference a depreciation schedule"))
			return

		if not (self.asset and self.asset_depreciation_schedule and self.depreciation_schedule_row):
			frappe.throw(_("Depreciation Entries are created from an Asset Depreciation Schedule"))

		row = frappe.db.get_value(
			"Depreciation Schedule",
			self.depreciation_schedule_row,
			["parent", "journal_entry"],
			as_dict=True,
		)
		if not row or row.parent != self.asset_depreciation_schedule:
			frappe.throw(
				_("Depreciation schedule row does not belong to {0}").format(self.asset_depreciation_schedule)
			)
		if (
			frappe.db.get_value("Asset Depreciation Schedule", self.asset_depreciation_schedule, "docstatus")
			!= 1
		):
			frappe.throw(
				_("Asset Depreciation Schedule {0} is not active").format(self.asset_depreciation_schedule)
			)
		if row.journal_entry and row.journal_entry != self.name:
			frappe.throw(
				_("Depreciation for this period is already posted in {0}").format(
					frappe.bold(row.journal_entry)
				),
				DuplicateDepreciationError,
			)
		duplicate = frappe.db.get_value(
			"Journal Entry",
			{
				"depreciation_schedule_row": self.depreciation_schedule_row,
				"docstatus": 1,
				"name": ("!=", self.name),
			},
		)
		if duplicate:
			frappe.throw(
				_("Depreciation for this period is already posted in {0}").format(frappe.bold(duplicate)),
				DuplicateDepreciationError,
			)

	def validate_recurring_reference(self):
		from spend.spend.doctype.recurring_payment.recurring_payment import validate_recurring_reference

		validate_recurring_reference(self)

	def before_submit(self):
		from spend.spend.doctype.budget.budget import (
			validate_expense_against_budget,
			validate_project_budget,
		)

		check_approved(self)
		validate_expense_against_budget(self)
		validate_project_budget(
			self, [(r.account, r.project, flt(r.debit) - flt(r.credit)) for r in self.accounts]
		)
		validate_category_budget(
			self,
			[
				(
					r.account,
					r.project,
					r.expense_category,
					r.expense_sub_category,
					flt(r.debit) - flt(r.credit),
				)
				for r in self.accounts
			],
		)

	def on_submit(self):
		make_gl_entries(self.get_gl_map())
		notify_budget_usage(
			self, [(r.account, r.cost_center, r.project, flt(r.debit) - flt(r.credit)) for r in self.accounts]
		)
		if self.voucher_type == "Depreciation Entry":
			from spend.spend.depreciation import on_depreciation_entry_submit

			on_depreciation_entry_submit(self)
		if self.voucher_type == "Recurring Payment":
			from spend.spend.doctype.recurring_payment.recurring_payment import on_recurring_entry_submit

			on_recurring_entry_submit(self)

	def before_cancel(self):
		self.ignore_linked_doctypes = (
			"GL Entry",
			"Asset",
			"Asset Depreciation Schedule",
			"Depreciation Schedule",
			"Recurring Payment",
			"Recurring Payment Schedule",
		)
		if self.voucher_type == "Depreciation Entry":
			from spend.spend.depreciation import validate_depreciation_entry_cancel

			validate_depreciation_entry_cancel(self)
		if self.voucher_type == "Asset Capitalization" and not self.flags.from_asset:
			if frappe.db.get_value("Asset", self.asset, "docstatus") == 1:
				frappe.throw(
					_("Cancel Asset {0} to reverse its capitalization").format(frappe.bold(self.asset))
				)

	def on_cancel(self):
		make_reverse_gl_entries(self.doctype, self.name)
		if self.voucher_type == "Depreciation Entry":
			from spend.spend.depreciation import on_depreciation_entry_cancel

			on_depreciation_entry_cancel(self)
		if self.voucher_type == "Recurring Payment":
			from spend.spend.doctype.recurring_payment.recurring_payment import on_recurring_entry_cancel

			on_recurring_entry_cancel(self)

	def on_trash(self):
		if self.voucher_type in ("Depreciation Entry", "Asset Capitalization") and self.docstatus == 2:
			frappe.throw(_("Cancelled asset entries are kept for the audit trail and cannot be deleted"))

	def get_gl_map(self) -> list[dict]:
		return [
			{
				"posting_date": self.posting_date,
				"fiscal_year": self.fiscal_year,
				"company": self.company,
				"account": row.account,
				"cost_center": row.cost_center,
				"project": row.project,
				"expense_category": row.expense_category,
				"expense_sub_category": row.expense_sub_category,
				"debit": row.debit,
				"credit": row.credit,
				"currency": self.currency,
				"voucher_type": self.doctype,
				"voucher_no": self.name,
				"voucher_subtype": self.voucher_type,
				"voucher_detail_no": row.name,
				"party_type": row.party_type,
				"party": row.party,
				"reference_type": row.reference_type,
				"reference_name": row.reference_name,
				"remarks": row.user_remark or self.user_remark,
			}
			for row in self.accounts
		]


class DuplicateDepreciationError(frappe.ValidationError):
	pass


def validate_party(row):
	"""A party may only be set on payable rows, and needs both its type and name."""
	if not (row.party_type or row.party):
		return
	if not (row.party_type and row.party):
		frappe.throw(_("Row {0}: Set both Party Type and Party").format(row.idx))
	if frappe.db.get_value("Account", row.account, "account_type") != "Payable":
		frappe.throw(_("Row {0}: Party can only be set on a Payable account").format(row.idx))


def validate_cost_center(cost_center: str, company: str, idx=None):
	prefix = _("Row {0}: ").format(idx) if idx else ""
	validate_company_link("Cost Center", cost_center, company, prefix + _("Cost Center"))
	is_group, disabled = frappe.db.get_value("Cost Center", cost_center, ["is_group", "disabled"])
	if is_group:
		frappe.throw(
			prefix
			+ _("Cost Center {0} is a group. Select a ledger cost center.").format(frappe.bold(cost_center))
		)
	if disabled:
		frappe.throw(prefix + _("Cost Center {0} is disabled").format(frappe.bold(cost_center)))
