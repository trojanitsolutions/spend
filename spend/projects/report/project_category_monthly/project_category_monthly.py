# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

from spend.spend.accounting import GL_PRECISION, get_company_currency
from spend.spend.expense_category import build_periods, get_category_monthly, get_months
from spend.spend.report_utils import currency_column, default_fiscal_year_dates, require_company


def execute(filters=None):
	filters = frappe._dict(filters or {})
	require_company(filters)
	if filters.project:
		frappe.has_permission("Project", "read", filters.project, throw=True)
	period = filters.period or "Monthly"
	from_date, to_date = default_fiscal_year_dates(filters)
	if period == "Yearly":
		from_date = get_earlier_year_start(from_date)
	entries = get_category_monthly(
		from_date,
		to_date,
		company=filters.company,
		project=filters.project,
		category=filters.expense_category,
	)
	costing = build_periods(entries, get_months(from_date, to_date), period)
	rows, periods = costing["rows"], costing["periods"]
	currency = get_company_currency(filters.company)
	return (
		get_columns(periods),
		get_data(rows, currency),
		None,
		get_chart(rows, periods),
		get_summary(rows, periods, period, currency),
	)


def get_earlier_year_start(from_date):
	"""The start of the fourth Fiscal Year before `from_date`, so Yearly compares five years."""
	starts = frappe.get_all(
		"Fiscal Year",
		filters={"disabled": 0, "start_date": ("<", from_date)},
		order_by="start_date desc",
		limit=4,
		pluck="start_date",
	)
	return starts[-1] if starts else from_date


def get_fieldname(key: str) -> str:
	return key.replace("-", "_").replace(" ", "_")


def get_columns(periods):
	return [
		{
			"fieldname": "category",
			"label": _("Category"),
			"fieldtype": "Link",
			"options": "Expense Category",
			"width": 220,
		},
		{"fieldname": "parent_category", "label": _("Parent"), "fieldtype": "Data", "hidden": 1},
		*(currency_column(get_fieldname(p["key"]), p["label"], 110) for p in periods),
		currency_column("total", _("Total")),
	]


def get_data(rows, currency):
	return [
		{
			"category": row["sub_category"] or row["category"],
			"parent_category": row["category"] if row["sub_category"] else None,
			"indent": row["indent"],
			"currency": currency,
			**{get_fieldname(key): amount for key, amount in row["months"].items()},
			"total": row["total"],
		}
		for row in rows
	]


def get_chart(rows, periods):
	parents = [row for row in rows if not row["indent"] and row["total"]][:8]
	if not parents:
		return None
	return {
		"data": {
			"labels": [p["label"] for p in periods],
			"datasets": [
				{"name": row["category"], "values": [row["months"][p["key"]] for p in periods]}
				for row in parents
			],
		},
		"type": "bar",
		"barOptions": {"stacked": 1},
		"fieldtype": "Currency",
	}


def get_summary(rows, periods, period, currency):
	parents = [row for row in rows if not row["indent"]]
	total = flt(sum(row["total"] for row in parents), GL_PRECISION)
	charged = [p for p in periods if any(row["months"][p["key"]] for row in parents)]
	average = {"Quarterly": _("Quarterly Average"), "Yearly": _("Yearly Average")}.get(period, _("Monthly Average"))
	return [
		{"label": _("Charged"), "value": total, "datatype": "Currency", "currency": currency},
		{
			"label": average,
			"value": flt(total / len(charged), GL_PRECISION) if charged else 0,
			"datatype": "Currency",
			"currency": currency,
		},
		{"label": _("Categories"), "value": len(parents), "datatype": "Int"},
	]
