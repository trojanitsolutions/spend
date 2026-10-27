# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from spend.spend.accounting import GL_PRECISION
from spend.spend.depreciation import get_posted_depreciation
from spend.spend.report_utils import currency_column, require_company


def execute(filters=None):
	filters = frappe._dict(filters or {})
	require_company(filters)
	data = get_data(filters)
	return get_columns(), data, None, get_chart(data), get_summary(data)


def get_columns():
	return [
		{"fieldname": "asset", "label": _("Asset"), "fieldtype": "Link", "options": "Asset", "width": 150},
		{"fieldname": "asset_name", "label": _("Asset Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 150},
		{
			"fieldname": "cost_center",
			"label": _("Cost Center"),
			"fieldtype": "Link",
			"options": "Cost Center",
			"width": 140,
		},
		{"fieldname": "location", "label": _("Location"), "fieldtype": "Data", "width": 110},
		{"fieldname": "purchase_date", "label": _("Purchase Date"), "fieldtype": "Date", "width": 110},
		{
			"fieldname": "available_for_use_date",
			"label": _("Capitalized On"),
			"fieldtype": "Date",
			"width": 110,
		},
		{"fieldname": "depreciation_method", "label": _("Method"), "fieldtype": "Data", "width": 140},
		{
			"fieldname": "frequency_of_depreciation",
			"label": _("Frequency"),
			"fieldtype": "Data",
			"width": 100,
		},
		{"fieldname": "useful_life_years", "label": _("Life (Years)"), "fieldtype": "Float", "width": 90},
		currency_column("gross_purchase_amount", _("Gross Value")),
		currency_column("salvage_value", _("Salvage Value"), 120),
		currency_column("accumulated_depreciation", _("Accumulated Depreciation")),
		currency_column("book_value", _("Book Value")),
		{
			"fieldname": "currency",
			"label": _("Currency"),
			"fieldtype": "Link",
			"options": "Currency",
			"hidden": 1,
		},
	]


def get_data(filters):
	conditions = {"company": filters.company, "docstatus": ("!=", 2) if filters.include_drafts else 1}
	for field in ("status", "cost_center", "depreciation_method"):
		if filters.get(field):
			conditions[field] = filters.get(field)
	as_on_date = getdate(filters.as_on_date or nowdate())
	conditions["purchase_date"] = ("<=", as_on_date)

	assets = frappe.get_list(
		"Asset",
		filters=conditions,
		fields=[
			"name as asset",
			"asset_name",
			"status",
			"cost_center",
			"location",
			"purchase_date",
			"available_for_use_date",
			"depreciation_method",
			"frequency_of_depreciation",
			"useful_life_years",
			"gross_purchase_amount",
			"salvage_value",
			"currency",
			"calculate_depreciation",
		],
		order_by="available_for_use_date, name",
	)
	for asset in assets:
		accumulated = get_posted_depreciation(asset.asset, to_date=as_on_date)
		asset.accumulated_depreciation = accumulated
		asset.book_value = flt(asset.gross_purchase_amount - accumulated, GL_PRECISION)
		if not asset.calculate_depreciation:
			asset.depreciation_method = asset.frequency_of_depreciation = None
	return assets


def get_summary(data):
	if not data:
		return []
	currency = data[0].currency
	return [
		{"label": _("Assets"), "value": len(data), "datatype": "Int"},
		{
			"label": _("Gross Value"),
			"value": sum(d.gross_purchase_amount for d in data),
			"datatype": "Currency",
			"currency": currency,
		},
		{
			"label": _("Accumulated Depreciation"),
			"value": sum(d.accumulated_depreciation for d in data),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Orange",
		},
		{
			"label": _("Book Value"),
			"value": sum(d.book_value for d in data),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Green",
		},
	]


def get_chart(data):
	by_status = {}
	for row in data:
		by_status[row.status] = by_status.get(row.status, 0) + 1
	if not by_status:
		return None
	return {
		"data": {
			"labels": list(by_status),
			"datasets": [{"name": _("Assets"), "values": list(by_status.values())}],
		},
		"type": "donut",
	}
