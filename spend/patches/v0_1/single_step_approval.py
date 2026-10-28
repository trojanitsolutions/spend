import frappe

from spend.spend.approval import APPROVAL_DOCTYPES, PENDING_GM, setup_workflows


def execute():
	"""Approval is one step by the General Manager: documents waiting for the old manager step move on."""
	setup_workflows()
	for doctype in APPROVAL_DOCTYPES:
		frappe.db.set_value(
			doctype,
			{"workflow_state": "Pending Manager Approval", "docstatus": 0},
			"workflow_state",
			PENDING_GM,
			update_modified=False,
		)
