# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from spend.spend.report_utils import currency_column, require_company


def execute(filters=None):
	filters = frappe._dict(filters or {})
	require_company(filters)
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "asset", "label": _("Asset"), "fieldtype": "Link", "options": "Asset", "width": 140},
		{"fieldname": "asset_name", "label": _("Asset Name"), "fieldtype": "Data", "width": 170},
		{
			"fieldname": "schedule",
			"label": _("Schedule"),
			"fieldtype": "Link",
			"options": "Asset Depreciation Schedule",
			"width": 170,
		},
		{"fieldname": "schedule_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		currency_column("opening_book_value", _("Opening Book Value")),
		currency_column("depreciation_amount", _("Depreciation"), 120),
		currency_column("accumulated_depreciation_amount", _("Accumulated")),
		currency_column("closing_book_value", _("Closing Book Value")),
		{"fieldname": "posting_status", "label": _("Status"), "fieldtype": "Data", "width": 90},
		{
			"fieldname": "journal_entry",
			"label": _("Journal Entry"),
			"fieldtype": "Link",
			"options": "Journal Entry",
			"width": 130,
		},
	]


def get_data(filters):
	ads = frappe.qb.DocType("Asset Depreciation Schedule")
	row = frappe.qb.DocType("Depreciation Schedule")
	query = (
		frappe.qb.from_(ads)
		.join(row)
		.on(row.parent == ads.name)
		.select(
			ads.asset,
			ads.asset_name,
			ads.name.as_("schedule"),
			row.schedule_date,
			row.opening_book_value,
			row.depreciation_amount,
			row.accumulated_depreciation_amount,
			row.closing_book_value,
			row.journal_entry,
		)
		.where((ads.docstatus == 1) & (ads.company == filters.company))
		.orderby(ads.asset)
		.orderby(row.idx)
	)
	if filters.asset:
		query = query.where(ads.asset == filters.asset)
	if filters.cost_center:
		query = query.where(ads.cost_center == filters.cost_center)
	if filters.from_date:
		query = query.where(row.schedule_date >= getdate(filters.from_date))
	if filters.to_date:
		query = query.where(row.schedule_date <= getdate(filters.to_date))
	if filters.posting_status == "Posted":
		query = query.where(row.journal_entry.isnotnull() & (row.journal_entry != ""))
	elif filters.posting_status == "Not Posted":
		query = query.where(row.journal_entry.isnull() | (row.journal_entry == ""))

	allowed = set(frappe.get_list("Asset", filters={"company": filters.company}, pluck="name"))
	today = getdate(nowdate())
	data = []
	for d in query.run(as_dict=True):
		if d.asset not in allowed:
			continue
		d.posting_status = (
			"Posted" if d.journal_entry else ("Due" if getdate(d.schedule_date) <= today else "Upcoming")
		)
		data.append(d)
	return data
