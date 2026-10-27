# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from spend.spend.accounting import GL_PRECISION


class Item(Document):
	def before_naming(self):
		self.item_code = (self.item_code or "").strip()

	def validate(self):
		self.item_name = (self.item_name or "").strip() or self.item_code
		self.validate_uoms()
		self.validate_fixed_asset()
		if not self.is_fixed_asset:
			self.auto_create_assets = 0

	def validate_uoms(self):
		"""The stock UOM is always a row with factor 1; every other unit appears once."""
		if not any(row.uom == self.stock_uom for row in self.uoms):
			self.append("uoms", {"uom": self.stock_uom, "conversion_factor": 1})
		seen = set()
		for row in self.uoms:
			if row.uom in seen:
				frappe.throw(_("UOM {0} is repeated in the UOMs table").format(frappe.bold(row.uom)))
			seen.add(row.uom)
			if row.uom == self.stock_uom:
				row.conversion_factor = 1
			elif flt(row.conversion_factor) <= 0:
				frappe.throw(_("Row {0}: Conversion Factor must be greater than zero").format(row.idx))
		if self.purchase_uom and self.purchase_uom not in seen:
			frappe.throw(
				_("Add {0} to the UOMs table with its conversion factor").format(
					frappe.bold(self.purchase_uom)
				)
			)

	def validate_fixed_asset(self):
		if self.is_new() or self.is_fixed_asset == self.get_db_value("is_fixed_asset"):
			return
		if frappe.db.exists("Purchase Invoice Item", {"item_code": self.name, "docstatus": 1}):
			frappe.throw(_("Is Fixed Asset cannot change because submitted bills use this item"))

	def on_trash(self):
		if frappe.db.exists("Purchase Invoice Item", {"item_code": self.name}):
			frappe.throw(_("Cannot delete Item {0} because bills use it").format(frappe.bold(self.name)))


def get_conversion_factor(item_code: str, uom: str | None) -> float:
	"""How many stock units one `uom` holds for this item."""
	stock_uom = frappe.db.get_value("Item", item_code, "stock_uom")
	if not uom or uom == stock_uom:
		return 1.0
	factor = frappe.db.get_value(
		"UOM Conversion Detail", {"parenttype": "Item", "parent": item_code, "uom": uom}, "conversion_factor"
	)
	if not factor:
		frappe.throw(
			_("UOM {0} is not set on Item {1}. Add it to the item's UOMs table.").format(
				frappe.bold(uom), frappe.bold(item_code)
			)
		)
	return flt(factor)


def get_buying_rate(item_code: str, supplier: str | None = None) -> float:
	"""Rate per stock UOM: the last bill from this supplier, else the last bill, else the standard rate."""
	if supplier:
		bill = frappe.qb.DocType("Purchase Invoice")
		line = frappe.qb.DocType("Purchase Invoice Item")
		last = (
			frappe.qb.from_(line)
			.join(bill)
			.on(bill.name == line.parent)
			.select(line.rate, line.conversion_factor)
			.where((bill.docstatus == 1) & (bill.supplier == supplier) & (line.item_code == item_code))
			.orderby(bill.posting_date, order=frappe.qb.desc)
			.orderby(bill.creation, order=frappe.qb.desc)
			.limit(1)
			.run(as_dict=True)
		)
		if last:
			return flt(last[0].rate) / (flt(last[0].conversion_factor) or 1)
	rates = frappe.db.get_value("Item", item_code, ["last_purchase_rate", "standard_rate"], as_dict=True)
	return flt(rates.last_purchase_rate) or flt(rates.standard_rate)


def update_last_purchase_rate(item_codes):
	"""Store the rate per stock UOM of the latest submitted bill line of each item."""
	bill = frappe.qb.DocType("Purchase Invoice")
	line = frappe.qb.DocType("Purchase Invoice Item")
	for item_code in set(item_codes):
		last = (
			frappe.qb.from_(line)
			.join(bill)
			.on(bill.name == line.parent)
			.select(line.rate, line.conversion_factor)
			.where((bill.docstatus == 1) & (line.item_code == item_code))
			.orderby(bill.posting_date, order=frappe.qb.desc)
			.orderby(bill.creation, order=frappe.qb.desc)
			.limit(1)
			.run(as_dict=True)
		)
		rate = flt(last[0].rate) / (flt(last[0].conversion_factor) or 1) if last else 0
		frappe.db.set_value("Item", item_code, "last_purchase_rate", flt(rate, GL_PRECISION))


@frappe.whitelist()
def get_item_details(
	item_code: str, company: str, supplier: str | None = None, uom: str | None = None
) -> dict:
	"""What a new bill line takes from its item, as in ERPNext's get_item_details."""
	frappe.has_permission("Item", "read", item_code, throw=True)
	from spend.spend.doctype.item_group.item_group import get_item_group_defaults

	item = frappe.get_cached_doc("Item", item_code)
	uom = uom or item.purchase_uom or item.stock_uom
	conversion_factor = get_conversion_factor(item_code, uom)
	defaults = get_item_group_defaults(item.item_group, company)
	if item.is_fixed_asset:
		account = frappe.get_cached_value("Company", company, "fixed_asset_account")
	else:
		account = defaults.get("expense_account") or frappe.get_cached_value(
			"Company", company, "default_expense_account"
		)
	return {
		"item_name": item.item_name,
		"description": item.description or item.item_name,
		"item_group": item.item_group,
		"stock_uom": item.stock_uom,
		"uom": uom,
		"conversion_factor": conversion_factor,
		"uoms": [row.uom for row in item.uoms],
		"rate": flt(get_buying_rate(item_code, supplier) * conversion_factor, GL_PRECISION),
		"expense_account": account,
		"cost_center": defaults.get("buying_cost_center"),
		"is_fixed_asset": item.is_fixed_asset,
	}


@frappe.whitelist()
def get_uom_details(item_code: str, uom: str) -> dict:
	frappe.has_permission("Item", "read", item_code, throw=True)
	return {"conversion_factor": get_conversion_factor(item_code, uom)}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_item_uoms(doctype, txt, searchfield, start, page_len, filters):
	"""UOMs of one item, for the UOM field of a bill line."""
	if filters.get("item_code"):
		frappe.has_permission("Item", "read", filters["item_code"], throw=True)
	return frappe.get_all(
		"UOM Conversion Detail",
		filters={"parenttype": "Item", "parent": filters.get("item_code"), "uom": ("like", f"%{txt}%")},
		fields=["uom", "conversion_factor"],
		order_by="idx",
		limit_start=start,
		limit_page_length=page_len,
		as_list=True,
	)
