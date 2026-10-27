# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class SpendSettings(Document):
	def validate(self):
		if not 0 <= flt(self.budget_alert_threshold) <= 100:
			frappe.throw(_("Budget Alert Threshold must be between 0 and 100"))
		if self.bill_due_days and self.bill_due_days < 0:
			frappe.throw(_("Bills Due Within cannot be negative"))

	def on_update(self):
		from spend.spend.approval import sync_workflows

		sync_workflows(self)
