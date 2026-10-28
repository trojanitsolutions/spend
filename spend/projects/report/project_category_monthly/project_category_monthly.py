# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate

from spend.spend.accounting import GL_PRECISION, get_company_currency
from spend.spend.expense_category import build_monthly, get_category_monthly, get_months
from spend.spend.report_utils import currency_column, default_fiscal_year_dates, require_company


def execute(filters=None):
	filters = frappe._dict(filters or {})
	require_company(filters)
	if filters.project:
		frappe.has_permission("Project", "read", filters.project, throw=True)
	from_date, to_date = default_fiscal_year_dates(filters)
	months = get_months(from_date, to_date)
	entries = get_category_monthly(
		from_date,
		to_date,
		company=filters.company,
		project=filters.project,
		category=filters.expense_category,
	)
	rows = build_monthly(entries, months)
	currency = get_company_currency(filters.company)
	return (
		get_columns(months),
		get_data(rows, currency),
		None,
		get_chart(rows, months),
		get_summary(rows, months, currency),
	)


def get_month_label(month: str) -> str:
	return getdate(f"{month}-01").strftime("%b %Y")


def get_columns(months):
	return [
		{
			"fieldname": "category",
			"label": _("Category"),
			"fieldtype": "Link",
			"options": "Expense Category",
			"width": 220,
		},
		{"fieldname": "parent_category", "label": _("Parent"), "fieldtype": "Data", "hidden": 1},
		*(currency_column(month.replace("-", "_"), get_month_label(month), 110) for month in months),
		currency_column("total", _("Total")),
	]


def get_data(rows, currency):
	return [
		{
			"category": row["sub_category"] or row["category"],
			"parent_category": row["category"] if row["sub_category"] else None,
			"indent": row["indent"],
			"currency": currency,
			**{month.replace("-", "_"): amount for month, amount in row["months"].items()},
			"total": row["total"],
		}
		for row in rows
	]


def get_chart(rows, months):
	parents = [row for row in rows if not row["indent"] and row["total"]][:8]
	if not parents:
		return None
	return {
		"data": {
			"labels": [get_month_label(month) for month in months],
			"datasets": [
				{"name": row["category"], "values": [row["months"][month] for month in months]}
				for row in parents
			],
		},
		"type": "bar",
		"barOptions": {"stacked": 1},
		"fieldtype": "Currency",
	}


def get_summary(rows, months, currency):
	parents = [row for row in rows if not row["indent"]]
	total = flt(sum(row["total"] for row in parents), GL_PRECISION)
	charged = [m for m in months if any(row["months"][m] for row in parents)]
	return [
		{"label": _("Charged"), "value": total, "datatype": "Currency", "currency": currency},
		{
			"label": _("Monthly Average"),
			"value": flt(total / len(charged), GL_PRECISION) if charged else 0,
			"datatype": "Currency",
			"currency": currency,
		},
		{"label": _("Categories"), "value": len(parents), "datatype": "Int"},
	]
