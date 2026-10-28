# Copyright (c) 2026, Trojan IT Solutions and Contributors
# For license information, please see license.txt

"""Attachments and the activity timeline shown on document pages in the portal."""

import html
import json
import re

import frappe
from frappe import _
from frappe.desk.notifications import extract_mentions
from frappe.utils import cstr, escape_html, get_fullname, strip_html

COMMENT_TYPES = ("Comment", "Workflow", "Info", "Attachment", "Attachment Removed", "Edit")


@frappe.whitelist()
def get_activity(doctype: str, name: str) -> dict:
	doc = get_permitted_doc(doctype, name, "read")
	can_write = bool(doc.has_permission("write"))
	return {
		"attachments": get_attachments(doc, can_write),
		"timeline": get_timeline(doc),
	}


@frappe.whitelist(methods=["POST"])
def add_comment(doctype: str, name: str, content: str, mentions: list | str | None = None) -> dict:
	"""Anyone who can read a document may comment on it, as in Desk. `mentions` are the users
	tagged as "@Full Name"; Frappe notifies them when the comment is inserted."""
	doc = get_permitted_doc(doctype, name, "read")
	content = (content or "").strip()
	if not content:
		frappe.throw(_("Write a comment first"))
	if isinstance(mentions, str):
		mentions = frappe.parse_json(mentions)
	allowed = {u.user: u.full_name for u in get_mentionables(doc)}
	tagged = [(user, allowed[user]) for user in dict.fromkeys(mentions or ()) if user in allowed]
	comment = doc.add_comment("Comment", with_mentions(escape_html(content), tagged))
	return {"name": comment.name}


@frappe.whitelist()
def get_mentionable_users(doctype: str, name: str) -> list[dict]:
	return get_mentionables(get_permitted_doc(doctype, name, "read"))


def get_mentionables(doc) -> list[dict]:
	"""Users who may be tagged on `doc`: those who can open it, as Desk's mention list allows."""
	users = frappe.get_all(
		"User",
		filters={
			"enabled": 1,
			"user_type": "System User",
			"allowed_in_mentions": 1,
			"name": ("not in", ["Administrator", "Guest", frappe.session.user]),
		},
		fields=["name as user", "full_name", "user_image"],
		order_by="full_name",
	)
	return [u for u in users if frappe.has_permission(doc.doctype, "read", doc, user=u.user)]


def with_mentions(content: str, tagged: list[tuple[str, str]]) -> str:
	"""Turn each escaped "@Full Name" into the mention markup Desk's editor writes."""
	spans = {}
	for user, full_name in tagged:
		label = escape_html(full_name or user)
		spans[f"@{label}"] = (
			f'<span class="mention" data-id="{escape_html(user)}" data-value="{label}" '
			f'data-denotation-char="@">@{label}</span>'
		)
	if not spans:
		return content
	# one pass, longest first, so "@Ann" never splits a span already made for "@Anna Lee"
	pattern = "|".join(re.escape(key) for key in sorted(spans, key=len, reverse=True))
	return re.sub(pattern, lambda m: spans[m.group(0)], content)


@frappe.whitelist(methods=["POST"])
def remove_attachment(doctype: str, name: str, file: str) -> None:
	doc = get_permitted_doc(doctype, name, "read")
	attached = frappe.db.get_value(
		"File", file, ["attached_to_doctype", "attached_to_name", "owner"], as_dict=True
	)
	if not attached or (attached.attached_to_doctype, attached.attached_to_name) != (doctype, name):
		frappe.throw(_("This file is not attached to {0}").format(name))
	if not can_remove(attached.owner, bool(doc.has_permission("write"))):
		frappe.throw(_("You cannot remove this file"), frappe.PermissionError)
	frappe.delete_doc("File", file, ignore_permissions=True)


def get_permitted_doc(doctype: str, name: str, ptype: str):
	from spend.api import check_app_permission

	check_app_permission()
	doc = frappe.get_doc(doctype, name)
	doc.check_permission(ptype)
	return doc


def can_remove(owner: str, can_write: bool) -> bool:
	return can_write or owner == frappe.session.user


def get_attachments(doc, can_write: bool) -> list[dict]:
	files = frappe.get_all(
		"File",
		filters={"attached_to_doctype": doc.doctype, "attached_to_name": doc.name, "is_folder": 0},
		fields=["name", "file_name", "file_url", "file_size", "is_private", "owner", "creation"],
		order_by="creation desc",
	)
	for f in files:
		f.owner_name = get_fullname(f.owner)
		f.can_remove = can_remove(f.owner, can_write)
	return files


def get_timeline(doc) -> list[dict]:
	entries = [entry("Created", doc.owner, doc.creation, _("created this"))]

	versions = frappe.get_all(
		"Version",
		filters={"ref_doctype": doc.doctype, "docname": doc.name},
		fields=["owner", "creation", "data"],
	)
	meta = frappe.get_meta(doc.doctype)
	for v in versions:
		for text in describe_version(meta, json.loads(v.data or "{}")):
			entries.append(entry("Version", v.owner, v.creation, text))

	comments = frappe.get_all(
		"Comment",
		filters={
			"reference_doctype": doc.doctype,
			"reference_name": doc.name,
			"comment_type": ("in", COMMENT_TYPES),
		},
		fields=["name", "comment_type", "content", "comment_email", "owner", "creation"],
	)
	for c in comments:
		content = html.unescape(strip_html(c.content or "")).strip()
		if c.comment_type == "Workflow":
			content = _("moved to {0}").format(content)
		elif c.comment_type == "Attachment":
			content = _("attached {0}").format(content)
		elif c.comment_type == "Attachment Removed" and not content.lower().startswith("removed"):
			content = _("removed attachment {0}").format(content)
		item = entry(c.comment_type, c.comment_email or c.owner, c.creation, content)
		if c.comment_type == "Comment" and "mention" in (c.content or ""):
			item["mentions"] = [
				{"user": user, "full_name": get_fullname(user)}
				for user in dict.fromkeys(extract_mentions(c.content))
			]
		entries.append(item)

	entries.sort(key=lambda e: e["creation"], reverse=True)
	return entries


def describe_version(meta, data: dict) -> list[str]:
	"""Readable lines for one Version, like Desk's timeline."""
	lines = []
	changes = []
	for fieldname, old, new in data.get("changed") or []:
		if fieldname == "docstatus":
			if new == 1:
				lines.append(_("submitted this"))
			elif new == 2:
				lines.append(_("cancelled this"))
			continue
		if fieldname == "name":
			continue
		label = _(meta.get_label(fieldname))
		changes.append(_("{0} from {1} to {2}").format(label, show(old), show(new)))
	if changes:
		lines.insert(0, _("changed {0}").format(", ".join(changes)))

	for key, text in (("added", _("added {0} rows to {1}")), ("removed", _("removed {0} rows from {1}"))):
		counts = count_by_table(data.get(key) or [])
		lines += [text.format(count, _(meta.get_label(table))) for table, count in counts.items()]
	counts = count_by_table(data.get("row_changed") or [])
	lines += [_("changed {0} rows in {1}").format(count, _(meta.get_label(table))) for table, count in counts.items()]
	return lines


def count_by_table(rows: list) -> dict:
	counts = {}
	for row in rows:
		counts[row[0]] = counts.get(row[0], 0) + 1
	return counts


def show(value) -> str:
	value = strip_html(cstr(value)).strip()
	return value if value else _("empty")


def entry(kind: str, user: str, creation, text: str) -> dict:
	return {
		"type": kind,
		"user": user,
		"full_name": get_fullname(user),
		"creation": creation,
		"text": text,
	}
