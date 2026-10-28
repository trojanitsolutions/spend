# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

"""Desk boot changes for Spend."""

import frappe
from frappe.utils.modules import get_blocked_modules

SIDEBAR = "Spend"


def filter_sidebar(bootinfo):
	"""Drop links to modules blocked for this user from the Spend sidebar.

	The Spend sidebar holds every Spend module, so Frappe's own module gate, which hides whole
	sidebars, never reaches these links. DocPerm and report roles are already applied by Frappe,
	and a section left with no links is not drawn."""
	sidebar = (bootinfo.get("module_sidebars") or {}).get(SIDEBAR)
	blocked = set(get_blocked_modules())
	if not sidebar or not blocked:
		return

	sidebar["items"] = [item for item in sidebar["items"] if get_item_module(item) not in blocked]


def get_item_module(item: dict) -> str | None:
	if item.get("link_type") == "DocType":
		return frappe.get_meta(item["link_to"]).module
	if item.get("link_type") == "Report":
		return frappe.db.get_value("Report", item["link_to"], "module", cache=True)
	return None
