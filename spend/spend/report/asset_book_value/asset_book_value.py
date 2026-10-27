# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from spend.spend.accounting import GL_PRECISION, get_balance
from spend.spend.depreciation import get_posted_depreciation
from spend.spend.report_utils import currency_column, require_company


def execute(filters=None):
	filters = frappe._dict(filters or {})
	require_company(filters)
	data = get_data(filters)
	return get_columns(), data, None, get_chart(data)


def get_columns():
	return [
		{"fieldname": "asset", "label": _("Asset"), "fieldtype": "Link", "options": "Asset", "width": 140},
		{"fieldname": "asset_name", "label": _("Asset Name"), "fieldtype": "Data", "width": 180},
		{
			"fieldname": "fixed_asset_account",
			"label": _("Fixed Asset Account"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 180,
		},
		{
			"fieldname": "cost_center",
			"label": _("Cost Center"),
			"fieldtype": "Link",
			"options": "Cost Center",
			"width": 130,
		},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 140},
		currency_column("gross_value", _("Gross Value")),
		currency_column("accumulated_depreciation", _("Accumulated Depreciation")),
		currency_column("book_value", _("Book Value")),
		currency_column("salvage_value", _("Salvage Value"), 120),
		{
			"fieldname": "depreciated_percent",
			"label": _("Depreciated %"),
			"fieldtype": "Percent",
			"width": 110,
		},
	]


def get_data(filters):
	as_on_date = getdate(filters.as_on_date or nowdate())
	conditions = {"company": filters.company, "docstatus": 1, "available_for_use_date": ("<=", as_on_date)}
	if filters.fixed_asset_account:
		conditions["fixed_asset_account"] = filters.fixed_asset_account
	if filters.cost_center:
		conditions["cost_center"] = filters.cost_center
	assets = frappe.get_list(
		"Asset",
		filters=conditions,
		fields=[
			"name as asset",
			"asset_name",
			"fixed_asset_account",
			"cost_center",
			"status",
			"gross_purchase_amount",
			"salvage_value",
			"capitalization_entry",
		],
		order_by="fixed_asset_account, name",
	)
	for asset in assets:
		# capitalized assets take their gross value from the ledger
		asset.gross_value = (
			get_balance(
				account=asset.fixed_asset_account,
				reference_type="Asset",
				reference_name=asset.asset,
				to_date=as_on_date,
			)
			if asset.capitalization_entry
			else flt(asset.gross_purchase_amount)
		)
		asset.accumulated_depreciation = get_posted_depreciation(asset.asset, to_date=as_on_date)
		asset.book_value = flt(asset.gross_value - asset.accumulated_depreciation, GL_PRECISION)
		depreciable = flt(asset.gross_value - asset.salvage_value)
		asset.depreciated_percent = (
			flt(asset.accumulated_depreciation / depreciable * 100, 2) if depreciable > 0 else 0
		)
	return assets


def get_chart(data):
	by_account = {}
	for row in data:
		by_account[row.fixed_asset_account] = by_account.get(row.fixed_asset_account, 0) + row.book_value
	if not by_account:
		return None
	return {
		"data": {
			"labels": list(by_account),
			"datasets": [{"name": _("Book Value"), "values": list(by_account.values())}],
		},
		"type": "bar",
		"fieldtype": "Currency",
	}
