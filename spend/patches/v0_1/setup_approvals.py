import frappe

from spend.spend.approval import APPROVED, setup_workflows
from spend.spend.notifications import setup_notification_types
from spend.spend.setup import create_roles


def execute():
	create_roles()
	setup_notification_types()
	frappe.get_single("Spend Settings").save()  # store the defaults
	setup_workflows()
	# projects in use before approvals existed count as approved
	frappe.db.set_value(
		"Project", {"workflow_state": ("in", ("", None, "Draft"))}, "workflow_state", APPROVED
	)
