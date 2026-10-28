# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from spend.spend.report_utils import currency_column, require_company


def execute(filters=None):
	filters = frappe._dict(filters or {})
	require_company(filters)
	if not filters.fiscal_year:
		frappe.throw(_("Select a Fiscal Year"))
	data = get_data(filters)
	return get_columns(filters), data, None, get_chart(data, filters)


def get_columns(filters):
	columns = [
		{"fieldname": "budget", "label": _("Budget"), "fieldtype": "Link", "options": "Budget", "width": 160},
		{
			"fieldname": "cost_center",
			"label": _("Cost Center"),
			"fieldtype": "Link",
			"options": "Cost Center",
			"width": 150,
		},
		{
			"fieldname": "account",
			"label": _("Account"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 190,
		},
	]
	if filters.period == "Monthly":
		columns.append({"fieldname": "period", "label": _("Period"), "fieldtype": "Data", "width": 100})
	return [
		*columns,
		currency_column("budget_amount", _("Budget Amount")),
		currency_column("actual", _("Actual")),
		currency_column("remaining", _("Remaining")),
		{"fieldname": "utilization", "label": _("Utilization %"), "fieldtype": "Percent", "width": 110},
	]


def get_data(filters):
	conditions = {"company": filters.company, "fiscal_year": filters.fiscal_year, "docstatus": 1}
	if filters.cost_center:
		conditions["cost_center"] = filters.cost_center
	data = []
	for name in frappe.get_list("Budget", filters=conditions, pluck="name", order_by="cost_center"):
		budget = frappe.get_doc("Budget", name)
		rows = (
			budget.get_monthly_budget_vs_actual()
			if filters.period == "Monthly"
			else budget.get_budget_vs_actual()
		)
		for row in rows:
			if filters.account and row["account"] != filters.account:
				continue
			data.append(
				{
					"budget": budget.name,
					"cost_center": budget.cost_center,
					"account": row["account"],
					"period": row.get("period"),
					"budget_amount": row["budget"],
					"actual": row["actual"],
					"remaining": row["remaining"],
					"utilization": row["utilization"],
					"currency": budget.currency,
				}
			)
	return data


def get_chart(data, filters):
	if not data:
		return None
	key = "period" if filters.period == "Monthly" else "account"
	labels, budget, actual = [], {}, {}
	for row in data:
		label = row[key]
		if label not in budget:
			labels.append(label)
			budget[label] = actual[label] = 0
		budget[label] += row["budget_amount"]
		actual[label] += row["actual"]
	return {
		"data": {
			"labels": labels,
			"datasets": [
				{"name": _("Budget"), "values": [budget[x] for x in labels]},
				{"name": _("Actual"), "values": [actual[x] for x in labels]},
			],
		},
		"type": "bar",
		"fieldtype": "Currency",
	}
