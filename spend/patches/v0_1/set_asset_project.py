import frappe


def execute():
	"""Assets made from a bill take the project of their bill line, else of the bill."""
	for asset in frappe.get_all(
		"Asset",
		filters={"purchase_invoice": ("is", "set"), "project": ("is", "not set")},
		fields=["name", "purchase_invoice", "item_code"],
	):
		project = frappe.db.get_value(
			"Purchase Invoice Item",
			{"parent": asset.purchase_invoice, "item_code": asset.item_code, "project": ("is", "set")},
			"project",
		) or frappe.db.get_value("Purchase Invoice", asset.purchase_invoice, "project")
		if project:
			frappe.db.set_value("Asset", asset.name, "project", project, update_modified=False)
