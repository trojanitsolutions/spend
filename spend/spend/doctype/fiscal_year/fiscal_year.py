# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, add_years, getdate


class FiscalYear(Document):
	def validate(self):
		self.validate_dates()
		self.validate_overlap()

	def validate_dates(self):
		start, end = getdate(self.start_date), getdate(self.end_date)
		if start >= end:
			frappe.throw(_("Start Date must be before End Date"))
		if end > add_days(add_years(start, 1), -1):
			frappe.throw(_("A Fiscal Year cannot be longer than one year"))

	def validate_overlap(self):
		if self.disabled:
			return
		overlapping = frappe.db.get_value(
			"Fiscal Year",
			{
				"name": ("!=", self.name),
				"disabled": 0,
				"start_date": ("<=", self.end_date),
				"end_date": (">=", self.start_date),
			},
		)
		if overlapping:
			frappe.throw(_("Dates overlap with Fiscal Year {0}").format(frappe.bold(overlapping)))

	def on_trash(self):
		if frappe.db.exists("GL Entry", {"fiscal_year": self.name}):
			frappe.throw(
				_("Cannot delete Fiscal Year {0} because ledger entries exist in it").format(self.name)
			)
