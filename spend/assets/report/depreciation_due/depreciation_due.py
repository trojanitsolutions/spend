# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, nowdate

from spend.spend.report_utils import currency_column, require_company


def execute(filters=None):
	filters = frappe._dict(filters or {})
	require_company(filters)
	data = get_data(filters)
	return get_columns(), data, None, None, get_summary(data)


def get_columns():
	return [
		{"fieldname": "asset", "label": _("Asset"), "fieldtype": "Link", "options": "Asset", "width": 140},
		{"fieldname": "asset_name", "label": _("Asset Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "schedule_date", "label": _("Due Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "days_overdue", "label": _("Days Overdue"), "fieldtype": "Int", "width": 110},
		currency_column("depreciation_amount", _("Depreciation Due")),
		currency_column("closing_book_value", _("Book Value After")),
		{
			"fieldname": "depreciation_expense_account",
			"label": _("Expense Account"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 170,
		},
		{
			"fieldname": "cost_center",
			"label": _("Cost Center"),
			"fieldtype": "Link",
			"options": "Cost Center",
			"width": 140,
		},
		{
			"fieldname": "schedule",
			"label": _("Schedule"),
			"fieldtype": "Link",
			"options": "Asset Depreciation Schedule",
			"width": 170,
		},
	]


def get_data(filters):
	as_on_date = getdate(filters.as_on_date or nowdate())
	ads = frappe.qb.DocType("Asset Depreciation Schedule")
	row = frappe.qb.DocType("Depreciation Schedule")
	asset = frappe.qb.DocType("Asset")
	query = (
		frappe.qb.from_(ads)
		.join(row)
		.on(row.parent == ads.name)
		.join(asset)
		.on(asset.name == ads.asset)
		.select(
			ads.asset,
			ads.asset_name,
			ads.name.as_("schedule"),
			row.schedule_date,
			row.depreciation_amount,
			row.closing_book_value,
			asset.depreciation_expense_account,
			asset.cost_center,
		)
		.where(
			(ads.docstatus == 1)
			& (asset.docstatus == 1)
			& (ads.company == filters.company)
			& (row.schedule_date <= as_on_date)
			& (row.journal_entry.isnull() | (row.journal_entry == ""))
		)
		.orderby(row.schedule_date)
		.orderby(ads.asset)
	)
	if filters.cost_center:
		query = query.where(asset.cost_center == filters.cost_center)
	if filters.asset:
		query = query.where(ads.asset == filters.asset)

	allowed = set(frappe.get_list("Asset", filters={"company": filters.company}, pluck="name"))
	data = [d for d in query.run(as_dict=True) if d.asset in allowed]
	for d in data:
		d.days_overdue = date_diff(as_on_date, d.schedule_date)
	return data


def get_summary(data):
	return [
		{
			"label": _("Entries Due"),
			"value": len(data),
			"datatype": "Int",
			"indicator": "Orange" if data else "Green",
		},
		{"label": _("Assets"), "value": len({d.asset for d in data}), "datatype": "Int"},
		{"label": _("Amount Due"), "value": sum(d.depreciation_amount for d in data), "datatype": "Currency"},
	]
