import frappe


def execute():
	"""Accounts User is folded into Accounts Manager: give its users the Accounts Manager role."""
	if not frappe.db.exists("Role", "Accounts Manager"):
		return
	users = frappe.get_all(
		"Has Role", filters={"role": "Accounts User", "parenttype": "User"}, pluck="parent", distinct=True
	)
	for name in users:
		user = frappe.get_doc("User", name)
		if user.enabled and "Accounts Manager" not in {r.role for r in user.roles}:
			user.add_roles("Accounts Manager")
