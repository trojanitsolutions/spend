# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class GLEntry(Document):
	"""Immutable ledger row. Only created by submitting vouchers; never edited or deleted."""

	def validate(self):
		if not self.flags.from_voucher:
			frappe.throw(_("GL Entries are created only by submitting vouchers"))
		if not self.is_new():
			frappe.throw(_("GL Entries cannot be edited"))
		if self.debit and self.credit:
			frappe.throw(_("A GL Entry cannot have both debit and credit"))
		if self.debit < 0 or self.credit < 0:
			frappe.throw(_("GL Entry amounts cannot be negative"))

	def on_trash(self):
		frappe.throw(_("GL Entries cannot be deleted. Cancel the voucher to reverse them."))
