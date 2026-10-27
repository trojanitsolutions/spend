# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

from spend.spend.accounting import GL_PRECISION, get_fiscal_year
from spend.spend.report_utils import (
	currency_column,
	default_fiscal_year_dates,
	get_gl_totals,
	require_company,
	rollup_tree,
	set_indent,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	company = require_company(filters)
	from_date, to_date = default_fiscal_year_dates(filters)
	data = get_data(company, from_date, to_date)
	return get_columns(), data, None, get_chart(data)


def get_columns():
	return [
		{
			"fieldname": "cost_center",
			"label": _("Cost Center"),
			"fieldtype": "Link",
			"options": "Cost Center",
			"width": 260,
		},
		currency_column("spending", _("Spending"), 150),
		currency_column("budget", _("Budget"), 150),
		currency_column("variance", _("Remaining Budget"), 150),
		{"fieldname": "share", "label": _("Share of Total %"), "fieldtype": "Percent", "width": 130},
	]


def get_data(company, from_date, to_date):
	nodes = frappe.get_list(
		"Cost Center",
		filters={"company": company},
		fields=["name", "parent_cost_center", "lft", "rgt", "is_group"],
		order_by="lft",
	)
	spending = {
		name: {"spending": flt(row.debit - row.credit, GL_PRECISION)}
		for name, row in get_gl_totals(
			"cost_center", company, from_date, to_date, root_type="Expense"
		).items()
	}
	rollup_tree(nodes, spending, ("spending",), "parent_cost_center")

	# budgets of the fiscal year that the period starts in, rolled up like spending
	fiscal_year = get_fiscal_year(from_date, throw=False)
	budgets = {}
	if fiscal_year:
		for row in frappe.get_all(
			"Budget",
			filters={"company": company, "fiscal_year": fiscal_year, "docstatus": 1},
			fields=["cost_center", "total_budget"],
		):
			budgets.setdefault(row.cost_center, {"budget": 0})["budget"] += flt(row.total_budget)
	budget_nodes = [dict(n) for n in nodes]
	rollup_tree(budget_nodes, budgets, ("budget",), "parent_cost_center")

	total = sum(n["spending"] for n in nodes if not n.get("parent_cost_center")) or 0
	currency = frappe.get_cached_value("Company", company, "default_currency")
	for node, budget_node in zip(nodes, budget_nodes, strict=True):
		node["cost_center"] = node["name"]
		node["budget"] = budget_node["budget"]
		node["variance"] = flt(node["budget"] - node["spending"], GL_PRECISION) if node["budget"] else None
		node["share"] = flt(node["spending"] / total * 100, 2) if total else 0
		node["currency"] = currency
	set_indent(nodes, "parent_cost_center")
	return nodes


def get_chart(data):
	leaves = [d for d in data if not d["is_group"] and d["spending"]]
	if not leaves:
		return None
	return {
		"data": {
			"labels": [d["name"] for d in leaves],
			"datasets": [{"name": _("Spending"), "values": [d["spending"] for d in leaves]}],
		},
		"type": "pie",
		"fieldtype": "Currency",
	}
