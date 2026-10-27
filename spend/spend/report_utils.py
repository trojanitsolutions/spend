# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

"""Helpers shared by the spend script reports."""

import frappe
from frappe import _
from frappe.query_builder.functions import Coalesce, Sum
from frappe.utils import flt, getdate, nowdate

from spend.spend.accounting import GL_PRECISION, get_fiscal_year


def require_company(filters) -> str:
	if not filters.get("company"):
		frappe.throw(_("Select a Company"))
	frappe.has_permission("Company", "read", filters.company, throw=True)
	return filters.company


def currency_column(fieldname, label, width=140):
	return {
		"fieldname": fieldname,
		"label": label,
		"fieldtype": "Currency",
		"options": "currency",
		"width": width,
	}


def get_gl_totals(
	group_by: str, company: str, from_date=None, to_date=None, root_type: str | None = None
) -> dict[str, frappe._dict]:
	"""Sum posted GL debit/credit grouped by `account` or `cost_center`."""
	gle = frappe.qb.DocType("GL Entry")
	account = frappe.qb.DocType("Account")
	field = gle[group_by]
	query = (
		frappe.qb.from_(gle)
		.select(
			field.as_("name"),
			Coalesce(Sum(gle.debit), 0).as_("debit"),
			Coalesce(Sum(gle.credit), 0).as_("credit"),
		)
		.where((gle.is_cancelled == 0) & (gle.company == company) & field.isnotnull())
		.groupby(field)
	)
	if from_date:
		query = query.where(gle.posting_date >= getdate(from_date))
	if to_date:
		query = query.where(gle.posting_date <= getdate(to_date))
	if root_type:
		query = query.join(account).on(account.name == gle.account).where(account.root_type == root_type)
	return {row.name: row for row in query.run(as_dict=True)}


def rollup_tree(
	nodes: list[dict], values: dict[str, dict], keys: tuple[str, ...], parent_field: str
) -> list[dict]:
	"""Set each node's totals to its own values plus those of its descendants.
	`nodes` must be ordered by lft so children come after their parents."""
	by_name = {node["name"]: node for node in nodes}
	for node in nodes:
		own = values.get(node["name"]) or {}
		for key in keys:
			node[key] = flt(own.get(key))
	for node in reversed(nodes):
		parent = by_name.get(node.get(parent_field))
		if parent:
			for key in keys:
				parent[key] = flt(parent[key] + node[key], GL_PRECISION)
	return nodes


def set_indent(nodes: list[dict], parent_field: str):
	depth = {}
	for node in nodes:  # ordered by lft, so parents come first
		node["indent"] = depth.get(node.get(parent_field), -1) + 1
		depth[node["name"]] = node["indent"]


def default_fiscal_year_dates(filters):
	if filters.get("from_date") and filters.get("to_date"):
		return getdate(filters.from_date), getdate(filters.to_date)
	fiscal_year = filters.get("fiscal_year") or get_fiscal_year(nowdate(), throw=False)
	if not fiscal_year:
		frappe.throw(_("Set From Date and To Date, or create a Fiscal Year for today"))
	start, end = frappe.db.get_value("Fiscal Year", fiscal_year, ["start_date", "end_date"])
	return getdate(start), getdate(end)
