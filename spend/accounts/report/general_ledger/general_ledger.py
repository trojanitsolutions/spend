# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

"""Every posted ledger row in a period, with opening, running and closing balances."""

import frappe
from frappe import _
from frappe.query_builder.functions import Coalesce, Sum
from frappe.utils import flt, getdate

from spend.spend.accounting import GL_PRECISION, get_fiscal_year, get_subtree
from spend.spend.report_utils import currency_column, require_company

BALANCE_SHEET = ("Asset", "Liability", "Equity")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	require_company(filters)
	if not filters.from_date or not filters.to_date:
		frappe.throw(_("Select the From and To dates"))
	filters.from_date, filters.to_date = getdate(filters.from_date), getdate(filters.to_date)
	if filters.from_date > filters.to_date:
		frappe.throw(_("From Date must be before To Date"))
	filters.currency = frappe.get_cached_value("Company", filters.company, "default_currency")

	entries = get_entries(filters)
	if filters.group_by_account:
		data = []
		openings = get_opening(filters, by_account=True)
		for account in sorted({e.account for e in entries} | set(openings)):
			rows = [e for e in entries if e.account == account]
			data += get_section(filters, rows, openings.get(account, (0, 0)), account)
	else:
		data = get_section(filters, entries, get_opening(filters))
	return get_columns(), data, None, None, get_summary(entries)


def get_columns():
	return [
		{"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{
			"fieldname": "account",
			"label": _("Account"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 200,
		},
		currency_column("debit", _("Debit"), 120),
		currency_column("credit", _("Credit"), 120),
		currency_column("balance", _("Balance"), 130),
		{"fieldname": "voucher_type", "label": _("Voucher Type"), "fieldtype": "Data", "width": 130},
		{
			"fieldname": "voucher_no",
			"label": _("Voucher No"),
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 160,
		},
		{"fieldname": "party", "label": _("Supplier"), "fieldtype": "Data", "width": 140},
		{
			"fieldname": "cost_center",
			"label": _("Cost Center"),
			"fieldtype": "Link",
			"options": "Cost Center",
			"width": 140,
		},
		{
			"fieldname": "project",
			"label": _("Project"),
			"fieldtype": "Link",
			"options": "Project",
			"width": 120,
		},
		{"fieldname": "remarks", "label": _("Remarks"), "fieldtype": "Data", "width": 220},
		{"fieldname": "bold", "label": "", "fieldtype": "Check", "hidden": 1},
	]


def apply_filters(query, gle, filters):
	query = query.where((gle.is_cancelled == 0) & (gle.company == filters.company))
	if filters.account:
		query = query.where(gle.account.isin(get_subtree("Account", filters.account)))
	if filters.cost_center:
		query = query.where(gle.cost_center.isin(get_subtree("Cost Center", filters.cost_center)))
	if filters.project:
		query = query.where(gle.project == filters.project)
	if filters.party:
		query = query.where((gle.party_type == "Supplier") & (gle.party == filters.party))
	if filters.voucher_no:
		query = query.where(gle.voucher_no == filters.voucher_no)
	return query


def get_entries(filters) -> list[frappe._dict]:
	gle = frappe.qb.DocType("GL Entry")
	query = frappe.qb.from_(gle).select(
		gle.posting_date,
		gle.account,
		gle.debit,
		gle.credit,
		gle.voucher_type,
		gle.voucher_no,
		gle.party,
		gle.cost_center,
		gle.project,
		gle.remarks,
	)
	query = apply_filters(query, gle, filters).where(
		gle.posting_date.between(filters.from_date, filters.to_date)
	)
	return query.orderby(gle.posting_date).orderby(gle.creation).run(as_dict=True)


def get_opening(filters, by_account=False):
	"""Debit and credit before the From date. Income and expense accounts start again
	each fiscal year, so their opening counts only from the start of the year."""
	gle = frappe.qb.DocType("GL Entry")
	account = frappe.qb.DocType("Account")
	query = (
		frappe.qb.from_(gle)
		.join(account)
		.on(account.name == gle.account)
		.select(Coalesce(Sum(gle.debit), 0), Coalesce(Sum(gle.credit), 0))
		.where(gle.posting_date < filters.from_date)
	)
	fiscal_year = get_fiscal_year(filters.from_date, throw=False)
	if fiscal_year:
		year_start = frappe.db.get_value("Fiscal Year", fiscal_year, "start_date")
		query = query.where(account.root_type.isin(BALANCE_SHEET) | (gle.posting_date >= year_start))
	query = apply_filters(query, gle, filters)
	if not by_account:
		debit, credit = query.run()[0]
		return flt(debit, GL_PRECISION), flt(credit, GL_PRECISION)
	rows = query.select(gle.account).groupby(gle.account).run()
	return {
		name: (flt(debit, GL_PRECISION), flt(credit, GL_PRECISION))
		for debit, credit, name in rows
		if flt(debit - credit, GL_PRECISION)
	}


def get_section(filters, entries, opening, account=None) -> list[dict]:
	"""Closing, the period total, the entries newest first with their running balance, then the
	opening. Balances are worked out oldest first, so each row shows the balance after it."""
	currency = filters.currency
	opening_debit, opening_credit = opening
	balance = flt(opening_debit - opening_credit, GL_PRECISION)
	label = (lambda text: f"{text}: {account}") if account else (lambda text: text)
	data = [
		{
			"account": label(_("Opening")),
			"debit": opening_debit,
			"credit": opening_credit,
			"balance": balance,
			"currency": currency,
			"bold": 1,
		}
	]
	debit = credit = 0
	for e in entries:
		balance = flt(balance + e.debit - e.credit, GL_PRECISION)
		debit += e.debit
		credit += e.credit
		data.append({**e, "balance": balance, "currency": currency})
	data += [
		{
			"account": label(_("Total")),
			"debit": flt(debit, GL_PRECISION),
			"credit": flt(credit, GL_PRECISION),
			"currency": currency,
			"bold": 1,
		},
		{
			"account": label(_("Closing (Opening + Total)")),
			"debit": flt(opening_debit + debit, GL_PRECISION),
			"credit": flt(opening_credit + credit, GL_PRECISION),
			"balance": balance,
			"currency": currency,
			"bold": 1,
		},
	]
	return data[::-1]


def get_summary(entries):
	debit = flt(sum(e.debit for e in entries), GL_PRECISION)
	credit = flt(sum(e.credit for e in entries), GL_PRECISION)
	return [
		{"label": _("Debit"), "value": debit, "datatype": "Currency"},
		{"label": _("Credit"), "value": credit, "datatype": "Currency"},
		{"label": _("Entries"), "value": len(entries), "datatype": "Int"},
	]
