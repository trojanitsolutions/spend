# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

"""General ledger primitives shared by Journal Entry, Asset, Budget and the reports.

Every balance in the app is computed from `GL Entry` rows. GL rows are never
deleted or edited: cancelling a voucher flags its rows as cancelled and adds
reversing rows, so the audit trail stays complete.
"""

import frappe
from frappe import _
from frappe.query_builder.functions import Coalesce, Sum
from frappe.utils import flt, getdate

GL_PRECISION = 2


class FiscalYearError(frappe.ValidationError):
	pass


class GLImbalanceError(frappe.ValidationError):
	pass


def get_fiscal_year(date, throw=True) -> str | None:
	"""Return the name of the enabled fiscal year that contains `date`."""
	date = getdate(date)
	fiscal_year = frappe.db.get_value(
		"Fiscal Year",
		{"start_date": ("<=", date), "end_date": (">=", date), "disabled": 0},
		"name",
	)
	if not fiscal_year and throw:
		frappe.throw(
			_("Date {0} is not in any active Fiscal Year").format(frappe.format(date, "Date")),
			FiscalYearError,
		)
	return fiscal_year


def get_company_currency(company: str) -> str:
	return frappe.get_cached_value("Company", company, "default_currency")


def make_gl_entries(gl_map: list[dict]):
	"""Insert balanced GL entries. Each dict holds GL Entry fields."""
	if not gl_map:
		return
	validate_gl_map(gl_map)
	for entry in gl_map:
		gle = frappe.new_doc("GL Entry")
		gle.update(entry)
		gle.flags.ignore_permissions = True
		gle.flags.from_voucher = True
		gle.insert()


def validate_gl_map(gl_map: list[dict]):
	debit = sum(flt(d.get("debit"), GL_PRECISION) for d in gl_map)
	credit = sum(flt(d.get("credit"), GL_PRECISION) for d in gl_map)
	if abs(flt(debit - credit, GL_PRECISION)) >= 0.01:
		frappe.throw(
			_("Debit ({0}) and Credit ({1}) are not equal").format(debit, credit),
			GLImbalanceError,
		)


def make_reverse_gl_entries(voucher_type: str, voucher_no: str):
	"""Cancel the GL entries of a voucher by posting mirror entries.

	Original rows are flagged `is_cancelled` and kept; reversal rows are also
	flagged so that balances (which only read `is_cancelled = 0`) net to zero
	while the full history stays queryable.
	"""
	entries = frappe.get_all(
		"GL Entry",
		filters={"voucher_type": voucher_type, "voucher_no": voucher_no, "is_cancelled": 0},
		fields=["*"],
	)
	if not entries:
		return

	frappe.db.set_value(
		"GL Entry",
		{"voucher_type": voucher_type, "voucher_no": voucher_no, "is_cancelled": 0},
		"is_cancelled",
		1,
		update_modified=False,
	)

	for entry in entries:
		for key in ("name", "creation", "modified", "owner", "modified_by", "idx", "docstatus"):
			entry.pop(key, None)
		entry["debit"], entry["credit"] = entry["credit"], entry["debit"]
		entry["is_cancelled"] = 1
		entry["remarks"] = _("On cancellation of {0}").format(voucher_no)

		gle = frappe.new_doc("GL Entry")
		gle.update(entry)
		gle.flags.ignore_permissions = True
		gle.flags.from_voucher = True
		gle.insert()


def get_balance(
	account: str | None = None,
	cost_center: str | None = None,
	from_date=None,
	to_date=None,
	company: str | None = None,
	reference_type: str | None = None,
	reference_name: str | None = None,
	party_type: str | None = None,
	party: str | None = None,
	project: str | None = None,
) -> float:
	"""Debit minus credit of posted GL entries. Group accounts and cost centers
	include all of their descendants."""
	gle = frappe.qb.DocType("GL Entry")
	query = (
		frappe.qb.from_(gle)
		.select(Coalesce(Sum(gle.debit), 0) - Coalesce(Sum(gle.credit), 0))
		.where(gle.is_cancelled == 0)
	)
	if account:
		query = query.where(gle.account.isin(get_subtree("Account", account)))
	if cost_center:
		query = query.where(gle.cost_center.isin(get_subtree("Cost Center", cost_center)))
	if company:
		query = query.where(gle.company == company)
	if from_date:
		query = query.where(gle.posting_date >= getdate(from_date))
	if to_date:
		query = query.where(gle.posting_date <= getdate(to_date))
	if reference_type:
		query = query.where(gle.reference_type == reference_type)
	if reference_name:
		query = query.where(gle.reference_name == reference_name)
	if party_type:
		query = query.where(gle.party_type == party_type)
	if party:
		query = query.where(gle.party == party)
	if project:
		query = query.where(gle.project == project)
	return flt(query.run()[0][0], GL_PRECISION)


def get_subtree(doctype: str, name: str) -> list[str]:
	"""Return `name` and all its descendants in a nested-set doctype."""
	lft, rgt = frappe.db.get_value(doctype, name, ["lft", "rgt"]) or (None, None)
	if lft is None:
		return [name]
	return frappe.get_all(doctype, filters={"lft": (">=", lft), "rgt": ("<=", rgt)}, pluck="name")


def get_ancestors_with_self(doctype: str, name: str) -> list[str]:
	lft, rgt = frappe.db.get_value(doctype, name, ["lft", "rgt"]) or (None, None)
	if lft is None:
		return [name]
	return frappe.get_all(doctype, filters={"lft": ("<=", lft), "rgt": (">=", rgt)}, pluck="name")


def validate_company_link(doctype: str, name: str, company: str, label: str | None = None):
	"""Throw unless the linked master belongs to `company`."""
	if not name:
		return
	linked_company = frappe.db.get_value(doctype, name, "company")
	if linked_company != company:
		frappe.throw(
			_("{0} {1} does not belong to Company {2}").format(
				label or _(doctype), frappe.bold(name), frappe.bold(company)
			)
		)


def validate_ledger_account(account: str, company: str, label: str | None = None, root_types=None):
	"""Account must belong to the company, be a ledger, be enabled and (optionally) of a root type."""
	if not account:
		return
	details = frappe.db.get_value(
		"Account", account, ["company", "is_group", "disabled", "root_type"], as_dict=True
	)
	label = label or _("Account")
	if not details:
		frappe.throw(_("{0} {1} does not exist").format(label, account))
	if details.company != company:
		frappe.throw(
			_("{0} {1} does not belong to Company {2}").format(
				label, frappe.bold(account), frappe.bold(company)
			)
		)
	if details.is_group:
		frappe.throw(
			_("{0} {1} is a group account. Select a ledger account.").format(label, frappe.bold(account))
		)
	if details.disabled:
		frappe.throw(_("{0} {1} is disabled").format(label, frappe.bold(account)))
	if root_types and details.root_type not in root_types:
		frappe.throw(
			_("{0} {1} must be of root type {2}").format(
				label, frappe.bold(account), " / ".join(_(r) for r in root_types)
			)
		)


class InactiveProjectError(frappe.ValidationError):
	pass


def validate_project(project: str, company: str, label: str | None = None):
	"""Project must belong to the company and still be open for postings."""
	if not project:
		return
	label = label or _("Project")
	validate_company_link("Project", project, company, label)
	status = frappe.db.get_value("Project", project, "status")
	if status != "Open":
		frappe.throw(
			_("{0} {1} is {2}. Reopen it to book against it.").format(label, frappe.bold(project), _(status)),
			InactiveProjectError,
		)

	from spend.spend.approval import is_project_approved

	if not is_project_approved(project):
		frappe.throw(
			_("{0} {1} is not approved yet. Its budget needs approval before you book against it.").format(
				label, frappe.bold(project)
			),
			InactiveProjectError,
		)
