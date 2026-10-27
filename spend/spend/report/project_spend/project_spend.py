# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

from spend.spend.accounting import GL_PRECISION, get_company_currency
from spend.spend.doctype.project.project import get_bill_totals, get_spend_by_project, make_project_row
from spend.spend.report_utils import currency_column, require_company


def execute(filters=None):
	filters = frappe._dict(filters or {})
	require_company(filters)
	data = get_data(filters)
	return (
		get_columns(),
		data,
		None,
		get_chart(data),
		get_summary(data, get_company_currency(filters.company)),
	)


def get_columns():
	return [
		{"fieldname": "name", "label": _("Project"), "fieldtype": "Link", "options": "Project", "width": 110},
		{"fieldname": "project_name", "label": _("Project Name"), "fieldtype": "Data", "width": 200},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
		currency_column("budget_amount", _("Budget")),
		currency_column("spent", _("Spent")),
		currency_column("remaining", _("Remaining")),
		{"fieldname": "utilization", "label": _("Utilization %"), "fieldtype": "Percent", "width": 110},
		currency_column("billed", _("Billed")),
		currency_column("paid", _("Paid")),
		currency_column("outstanding", _("Outstanding")),
	]


def get_data(filters) -> list[dict]:
	project_filters = {"company": filters.company}
	if filters.project:
		project_filters["name"] = filters.project
	if filters.status:
		project_filters["status"] = filters.status
	projects = frappe.get_list(
		"Project",
		filters=project_filters,
		fields=["name", "project_name", "status", "budget_amount", "currency"],
		order_by="creation desc",
		limit=0,
	)
	currency = get_company_currency(filters.company)
	for project in projects:
		project.currency = project.currency or currency
	names = [p.name for p in projects]
	spend = get_spend_by_project(filters.company, names)
	bills = get_bill_totals(names)
	return [make_project_row(p, spend.get(p.name, 0.0), bills.get(p.name)) for p in projects]


def get_summary(data, currency):
	budget = flt(sum(flt(d["budget_amount"]) for d in data), GL_PRECISION)
	spent = flt(sum(d["spent"] for d in data), GL_PRECISION)
	over = sum(1 for d in data if d["remaining"] is not None and d["remaining"] < 0)
	return [
		{"label": _("Budget"), "value": budget, "datatype": "Currency", "currency": currency},
		{"label": _("Spent"), "value": spent, "datatype": "Currency", "currency": currency},
		{
			"label": _("Owed to Suppliers"),
			"value": flt(sum(d["outstanding"] for d in data), GL_PRECISION),
			"datatype": "Currency",
			"currency": currency,
		},
		{
			"label": _("Over Budget"),
			"value": over,
			"datatype": "Int",
			"indicator": "Red" if over else "Green",
		},
	]


def get_chart(data):
	rows = [d for d in data if d["spent"] or flt(d["budget_amount"])][:12]
	if not rows:
		return None
	return {
		"data": {
			"labels": [d["project_name"] for d in rows],
			"datasets": [
				{"name": _("Budget"), "values": [flt(d["budget_amount"]) for d in rows]},
				{"name": _("Spent"), "values": [d["spent"] for d in rows]},
			],
		},
		"type": "bar",
		"fieldtype": "Currency",
	}
