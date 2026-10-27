import frappe

from spend.spend.doctype.item_group.item_group import ROOT
from spend.spend.setup import setup_items


def execute():
	setup_items()
	# items made before UOMs and groups existed kept their unit as text in `uom`
	old_uom = frappe.db.has_column("Item", "uom")
	for name in frappe.get_all("Item", pluck="name"):
		item = frappe.get_doc("Item", name)
		unit = (old_uom and frappe.db.get_value("Item", name, "uom")) or item.stock_uom or "Nos"
		if not frappe.db.exists("UOM", unit):
			frappe.get_doc({"doctype": "UOM", "uom_name": unit}).insert(ignore_permissions=True)
		item.stock_uom = unit
		item.item_group = item.item_group or ROOT
		item.flags.ignore_permissions = True
		item.save()

	line = frappe.qb.DocType("Purchase Invoice Item")
	(
		frappe.qb.update(line)
		.set(line.conversion_factor, 1)
		.set(line.stock_qty, line.qty)
		.set(line.stock_uom, line.uom)
		.where((line.conversion_factor == 0) | line.conversion_factor.isnull())
		.run()
	)
