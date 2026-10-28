# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

"""Desk is for System Managers. Everyone else works in /spend."""

import frappe
from werkzeug.routing import RequestRedirect

DESK_ROLE = "System Manager"
DESK_PATHS = ("/desk", "/app", "/apps")


def has_desk_access(user: str | None = None) -> bool:
	return DESK_ROLE in frappe.get_roles(user)


def is_desk_path(path: str) -> bool:
	path = path.rstrip("/") or "/"
	return path in DESK_PATHS or path.startswith(("/desk/", "/app/"))


def redirect_from_desk():
	"""before_request: send a signed-in user without Desk access to /spend. Desk is routed
	before any page renderer hook, so the redirect has to happen here. Werkzeug's
	RequestRedirect is answered as a plain redirect, where frappe.Redirect would be a 500."""
	request = getattr(frappe.local, "request", None)
	if not request or not is_desk_path(request.path):
		return
	if frappe.session.user == "Guest" or has_desk_access():
		return
	raise RequestRedirect("/spend")
