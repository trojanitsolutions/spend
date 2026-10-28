# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder.functions import Coalesce, Sum
from frappe.utils import date_diff, flt, getdate, nowdate

from spend.spend.accounting import GL_PRECISION
from spend.spend.report_utils import currency_column, require_company

# (fieldname, label, first day overdue, last day overdue)
AGEING_BUCKETS = (
	("not_due", _("Not Yet Due"), None, 0),
	("range_1", _("1-30 Days"), 1, 30),
	("range_2", _("31-60 Days"), 31, 60),
	("range_3", _("61-90 Days"), 61, 90),
	("range_4", _("90+ Days"), 91, None),
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	require_company(filters)
	filters.as_on_date = getdate(filters.as_on_date or nowdate())
	data = get_data(filters)
	return get_columns(), data, None, get_chart(data), get_summary(data)


def get_columns():
	return [
		{
			"fieldname": "supplier",
			"label": _("Supplier"),
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 200,
		},
		{"fieldname": "bills", "label": _("Open Bills"), "fieldtype": "Int", "width": 90},
		currency_column("invoiced", _("Invoiced")),
		currency_column("paid", _("Paid")),
		currency_column("outstanding", _("Outstanding")),
		*(currency_column(fieldname, label, 110) for fieldname, label, _first, _last in AGEING_BUCKETS),
	]


def get_bill_balances(company: str, as_on_date, supplier: str | None = None) -> list[frappe._dict]:
	"""Invoiced and paid per supplier bill, from posted payable ledger rows up to `as_on_date`."""
	gle = frappe.qb.DocType("GL Entry")
	invoice = frappe.qb.DocType("Purchase Invoice")
	query = (
		frappe.qb.from_(gle)
		.join(invoice)
		.on(invoice.name == gle.reference_name)
		.select(
			gle.party.as_("supplier"),
			gle.reference_name.as_("invoice"),
			invoice.due_date,
			Coalesce(Sum(gle.credit), 0).as_("invoiced"),
			Coalesce(Sum(gle.debit), 0).as_("paid"),
		)
		.where(
			(gle.is_cancelled == 0)
			& (gle.company == company)
			& (gle.party_type == "Supplier")
			& (gle.reference_type == "Purchase Invoice")
			& (gle.posting_date <= as_on_date)
		)
		.groupby(gle.party, gle.reference_name, invoice.due_date)
	)
	if supplier:
		query = query.where(gle.party == supplier)
	return query.run(as_dict=True)


def get_bucket(days_overdue: int) -> str:
	for fieldname, _label, first, last in AGEING_BUCKETS:
		if (first is None or days_overdue >= first) and (last is None or days_overdue <= last):
			return fieldname
	return AGEING_BUCKETS[-1][0]


def get_data(filters) -> list[dict]:
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	suppliers = {}
	for bill in get_bill_balances(filters.company, filters.as_on_date, filters.supplier):
		row = suppliers.setdefault(
			bill.supplier,
			{
				"supplier": bill.supplier,
				"bills": 0,
				"invoiced": 0.0,
				"paid": 0.0,
				"outstanding": 0.0,
				"currency": currency,
				**{fieldname: 0.0 for fieldname, *_rest in AGEING_BUCKETS},
			},
		)
		outstanding = flt(bill.invoiced - bill.paid, GL_PRECISION)
		row["invoiced"] = flt(row["invoiced"] + bill.invoiced, GL_PRECISION)
		row["paid"] = flt(row["paid"] + bill.paid, GL_PRECISION)
		if outstanding <= 0:
			continue
		bucket = get_bucket(date_diff(filters.as_on_date, bill.due_date))
		row["bills"] += 1
		row["outstanding"] = flt(row["outstanding"] + outstanding, GL_PRECISION)
		row[bucket] = flt(row[bucket] + outstanding, GL_PRECISION)

	data = [row for row in suppliers.values() if row["outstanding"] or filters.show_settled]
	return sorted(data, key=lambda row: -row["outstanding"])


def get_summary(data):
	outstanding = sum(d["outstanding"] for d in data)
	not_due = sum(d["not_due"] for d in data)
	return [
		{"label": _("Outstanding"), "value": outstanding, "datatype": "Currency"},
		{
			"label": _("Overdue"),
			"value": outstanding - not_due,
			"datatype": "Currency",
			"indicator": "Red" if outstanding - not_due > 0 else "Green",
		},
		{"label": _("Suppliers Owed"), "value": sum(1 for d in data if d["outstanding"]), "datatype": "Int"},
	]


def get_chart(data):
	if not data:
		return None
	return {
		"data": {
			"labels": [label for _fieldname, label, *_rest in AGEING_BUCKETS],
			"datasets": [
				{
					"name": _("Outstanding"),
					"values": [
						flt(sum(d[fieldname] for d in data), GL_PRECISION)
						for fieldname, *_rest in AGEING_BUCKETS
					],
				}
			],
		},
		"type": "bar",
		"fieldtype": "Currency",
	}
