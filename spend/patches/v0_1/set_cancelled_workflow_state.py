import frappe

from spend.spend.approval import APPROVAL_DOCTYPES, CANCELLED


def execute():
	"""Cancelled documents kept the state they had before cancel; mark them Cancelled."""
	for doctype in APPROVAL_DOCTYPES:
		if frappe.get_meta(doctype).is_submittable:
			frappe.db.set_value(
				doctype,
				{"docstatus": 2, "workflow_state": ("not in", (CANCELLED, "", None))},
				"workflow_state",
				CANCELLED,
				update_modified=False,
			)
