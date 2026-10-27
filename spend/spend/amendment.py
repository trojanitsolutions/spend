# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

"""Revise a submitted Budget or Recurring Payment: cancel it, then amend a copy.

The copy keeps `amended_from`, gets the next name (BUD-2026-0001-1, -2, ...) and
goes through approval like a new document. Only one amendment is open at a time.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, fmt_money, getdate

from spend.spend.accounting import GL_PRECISION

AMENDABLE = ("Budget", "Recurring Payment")
TOTAL_FIELDS = {"Budget": "total_budget", "Recurring Payment": "total_amount"}
# fields an amendment must keep; anything else is a new document
FIXED_FIELDS = {"Budget": ("company", "cost_center", "fiscal_year"), "Recurring Payment": ("company",)}


@frappe.whitelist()
def get_amendment(doctype: str, name: str) -> dict:
	"""An unsaved copy of a cancelled document to edit, or the amendment already open for it."""
	if doctype not in AMENDABLE:
		frappe.throw(_("{0} cannot be amended here").format(_(doctype)))
	source = frappe.get_doc(doctype, name)
	source.check_permission("read")
	if not frappe.has_permission(doctype, "create"):
		frappe.throw(_("Not permitted to amend {0}").format(name), frappe.PermissionError)
	if source.docstatus != 2:
		frappe.throw(_("Cancel {0} {1} before amending it").format(_(doctype), frappe.bold(name)))

	existing = get_amended_as(doctype, name)
	if existing and existing.docstatus == 0:
		return {"existing": existing.name}
	if existing:
		frappe.throw(_("{0} was already amended as {1}").format(name, frappe.bold(existing.name)))

	doc = frappe.copy_doc(source, ignore_no_copy=False)
	for d in [doc, *doc.get_all_children()]:
		d.docstatus = 0
	doc.amended_from = name
	previous = {"name": name, "total": flt(source.get(TOTAL_FIELDS[doctype]))}
	if doctype == "Recurring Payment":
		previous.update(set_unpaid_part(doc, source))
	return {"doc": doc.as_dict(), "previous": previous}


def set_unpaid_part(doc, source) -> dict:
	"""The amendment of a recurring payment covers only what the cancelled one did not pay."""
	posted = [r for r in source.schedule if r.journal_entry]
	unpaid = [r for r in source.schedule if not r.journal_entry]
	paid = flt(sum(flt(r.amount) for r in posted), GL_PRECISION)
	last_paid = max((getdate(r.payment_date) for r in posted), default=None)

	if unpaid:
		doc.from_date = min(getdate(r.payment_date) for r in unpaid)
	elif last_paid:
		doc.from_date = add_days(last_paid, 1)
	doc.total_amount = flt(flt(source.total_amount) - paid, GL_PRECISION)
	doc.set("schedule", [{"payment_date": r.payment_date, "amount": r.amount} for r in unpaid])
	return {"paid_amount": paid, "payments": len(posted), "last_paid": last_paid}


def get_amended_as(doctype: str, name: str):
	return frappe.db.get_value(
		doctype, {"amended_from": name}, ["name", "docstatus"], as_dict=True, order_by="creation desc"
	)


def validate_amendment(doc):
	"""Called from validate: an amendment needs a reason and keeps what makes it the same document."""
	if not doc.get("amended_from"):
		return
	if not (doc.amendment_reason or "").strip():
		frappe.throw(_("Give a reason for the amendment"))

	previous = frappe.db.get_value(doc.doctype, doc.amended_from, FIXED_FIELDS[doc.doctype], as_dict=True)
	for field in FIXED_FIELDS[doc.doctype]:
		if doc.get(field) != previous.get(field):
			frappe.throw(
				_("{0} cannot change in an amendment. Create a new {1} instead.").format(
					doc.meta.get_label(field), _(doc.doctype)
				)
			)

	if doc.is_new():
		existing = get_amended_as(doc.doctype, doc.amended_from)
		if existing:
			frappe.throw(
				_("{0} is already amended as {1}").format(doc.amended_from, frappe.bold(existing.name))
			)


def get_chain(doctype: str, name: str) -> list[str]:
	"""Every version of a document, oldest first."""
	first = name
	while previous := frappe.db.get_value(doctype, first, "amended_from"):
		first = previous
	chain = [first]
	while amended := get_amended_as(doctype, chain[-1]):
		chain.append(amended.name)
	return chain


@frappe.whitelist()
def get_versions(doctype: str, name: str) -> list[dict]:
	"""The versions of a document, oldest first, each with its change from the one before."""
	from spend.spend.approval import get_app_route

	if doctype not in AMENDABLE:
		frappe.throw(_("{0} cannot be amended here").format(_(doctype)))
	frappe.get_doc(doctype, name).check_permission("read")

	versions, previous = [], None
	for version in get_chain(doctype, name):
		doc = frappe.get_doc(doctype, version)
		total = flt(doc.get(TOTAL_FIELDS[doctype]), GL_PRECISION)
		row = {
			"name": doc.name,
			"docstatus": doc.docstatus,
			"workflow_state": doc.get("workflow_state"),
			"status": doc.get("status"),
			"total": total,
			"net_change": flt(total - previous["total"], GL_PRECISION)
			if previous and doctype == "Budget"
			else None,
			"reason": doc.get("amendment_reason"),
			"owner_name": frappe.utils.get_fullname(doc.owner),
			"modified": doc.modified,
			"route": get_app_route(doctype, doc.name),
		}
		if doctype == "Budget":
			row["accounts"] = {r.account: flt(r.budget_amount, GL_PRECISION) for r in doc.accounts}
			row["changes"] = get_account_changes(previous["accounts"], row["accounts"]) if previous else []
			row["action_if_exceeded"] = doc.action_if_exceeded
			row["budget_period"] = doc.budget_period
		versions.append(row)
		previous = row
	return versions


def get_account_changes(before: dict, after: dict) -> list[dict]:
	"""Each account whose amount differs, including accounts added or removed."""
	changes = []
	for account in [*before, *(a for a in after if a not in before)]:
		old, new = before.get(account, 0.0), after.get(account, 0.0)
		if old != new:
			changes.append(
				{"account": account, "before": old, "after": new, "change": flt(new - old, GL_PRECISION)}
			)
	return changes


def get_last_paid_date(doctype: str, name: str):
	"""Latest posted payment over every earlier version of a recurring payment."""
	row = frappe.qb.DocType("Recurring Payment Schedule")
	dates = (
		frappe.qb.from_(row)
		.select(row.payment_date)
		.where(row.parent.isin(get_chain(doctype, name)) & row.journal_entry.isnotnull())
		.orderby(row.payment_date, order=frappe.qb.desc)
		.limit(1)
		.run(pluck=True)
	)
	return getdate(dates[0]) if dates else None


def get_amendment_note(doc) -> str:
	"""What an approver needs to know about an amendment: what it replaces, the change and why."""
	if not doc.get("amended_from"):
		return ""
	field = TOTAL_FIELDS[doc.doctype]
	change = flt(flt(doc.get(field)) - flt(frappe.db.get_value(doc.doctype, doc.amended_from, field)))
	parts = [_("Amends {0}").format(doc.amended_from)]
	if doc.doctype == "Budget":
		sign = "+" if change > 0 else "-" if change < 0 else "±"
		parts.append(
			_("net change {0}{1}").format(sign, fmt_money(abs(change), currency=doc.get("currency")))
		)
	if doc.get("amendment_reason"):
		parts.append(doc.amendment_reason.strip())
	return " · ".join(parts)
