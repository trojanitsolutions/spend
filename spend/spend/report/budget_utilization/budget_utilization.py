# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

from spend.spend.accounting import GL_PRECISION
from spend.spend.report_utils import currency_column, require_company

NEAR_LIMIT = 80


def execute(filters=None):
	filters = frappe._dict(filters or {})
	require_company(filters)
	if not filters.fiscal_year:
		frappe.throw(_("Select a Fiscal Year"))
	data = get_data(filters)
	return get_columns(), data, None, get_chart(data), get_summary(data)


def get_columns():
	return [
		{"fieldname": "budget", "label": _("Budget"), "fieldtype": "Link", "options": "Budget", "width": 170},
		{
			"fieldname": "cost_center",
			"label": _("Cost Center"),
			"fieldtype": "Link",
			"options": "Cost Center",
			"width": 160,
		},
		{"fieldname": "budget_period", "label": _("Period"), "fieldtype": "Data", "width": 90},
		{"fieldname": "action_if_exceeded", "label": _("On Exceed"), "fieldtype": "Data", "width": 90},
		currency_column("allocated", _("Allocated")),
		currency_column("actual", _("Actual")),
		currency_column("remaining", _("Remaining")),
		{"fieldname": "utilization", "label": _("Utilization %"), "fieldtype": "Percent", "width": 110},
		{"fieldname": "utilization_status", "label": _("Status"), "fieldtype": "Data", "width": 110},
	]


def get_status(utilization: float) -> str:
	if utilization > 100:
		return "Exceeded"
	if utilization >= NEAR_LIMIT:
		return "Near Limit"
	return "On Track"


def get_data(filters):
	conditions = {"company": filters.company, "fiscal_year": filters.fiscal_year, "docstatus": 1}
	if filters.cost_center:
		conditions["cost_center"] = filters.cost_center
	data = []
	for name in frappe.get_list("Budget", filters=conditions, pluck="name", order_by="cost_center"):
		budget = frappe.get_doc("Budget", name)
		rows = budget.get_budget_vs_actual()
		allocated = flt(sum(r["budget"] for r in rows), GL_PRECISION)
		actual = flt(sum(r["actual"] for r in rows), GL_PRECISION)
		utilization = flt(actual / allocated * 100, 2) if allocated else 0
		data.append(
			{
				"budget": budget.name,
				"cost_center": budget.cost_center,
				"budget_period": budget.budget_period,
				"action_if_exceeded": budget.action_if_exceeded,
				"allocated": allocated,
				"actual": actual,
				"remaining": flt(allocated - actual, GL_PRECISION),
				"utilization": utilization,
				"utilization_status": get_status(utilization),
				"currency": budget.currency,
			}
		)
	return data


def get_summary(data):
	allocated = sum(d["allocated"] for d in data)
	actual = sum(d["actual"] for d in data)
	utilization = flt(actual / allocated * 100, 2) if allocated else 0
	return [
		{"label": _("Allocated"), "value": allocated, "datatype": "Currency"},
		{"label": _("Actual"), "value": actual, "datatype": "Currency"},
		{
			"label": _("Remaining"),
			"value": allocated - actual,
			"datatype": "Currency",
			"indicator": "Green" if allocated >= actual else "Red",
		},
		{
			"label": _("Utilization"),
			"value": utilization,
			"datatype": "Percent",
			"indicator": "Red" if utilization > 100 else "Blue",
		},
		{
			"label": _("Exceeded Budgets"),
			"value": sum(1 for d in data if d["utilization_status"] == "Exceeded"),
			"datatype": "Int",
		},
	]


def get_chart(data):
	if not data:
		return None
	return {
		"data": {
			"labels": [d["cost_center"] for d in data],
			"datasets": [{"name": _("Utilization %"), "values": [d["utilization"] for d in data]}],
		},
		"type": "bar",
		"fieldtype": "Percent",
	}
