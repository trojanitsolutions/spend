# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from spend.spend.accounting import GL_PRECISION
from spend.spend.report_utils import currency_column, get_gl_totals, require_company, rollup_tree, set_indent


def execute(filters=None):
	filters = frappe._dict(filters or {})
	company = require_company(filters)
	return get_columns(), get_data(company, filters)


def get_columns():
	return [
		{
			"fieldname": "account",
			"label": _("Account"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 300,
		},
		{"fieldname": "account_number", "label": _("Number"), "fieldtype": "Data", "width": 80},
		{"fieldname": "root_type", "label": _("Root Type"), "fieldtype": "Data", "width": 90},
		{"fieldname": "account_type", "label": _("Account Type"), "fieldtype": "Data", "width": 160},
		currency_column("debit", _("Debit")),
		currency_column("credit", _("Credit")),
		currency_column("balance", _("Balance (Dr - Cr)")),
	]


def get_data(company, filters):
	as_on_date = getdate(filters.as_on_date or nowdate())
	conditions = {"company": company}
	if filters.root_type:
		conditions["root_type"] = filters.root_type
	if not filters.include_disabled:
		conditions["disabled"] = 0
	nodes = frappe.get_list(
		"Account",
		filters=conditions,
		fields=[
			"name",
			"account_name",
			"parent_account",
			"account_number",
			"root_type",
			"account_type",
			"is_group",
			"lft",
			"rgt",
		],
		order_by="lft",
	)
	rollup_tree(
		nodes, get_gl_totals("account", company, to_date=as_on_date), ("debit", "credit"), "parent_account"
	)
	currency = frappe.get_cached_value("Company", company, "default_currency")
	for node in nodes:
		node["account"] = node["name"]
		node["balance"] = flt(node["debit"] - node["credit"], GL_PRECISION)
		node["currency"] = currency
	if not filters.show_zero_balances:
		nodes = [n for n in nodes if n["is_group"] or n["debit"] or n["credit"]]
	set_indent(nodes, "parent_account")
	return nodes
