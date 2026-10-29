from urllib.parse import quote

import frappe

from spend.spend.doctype.frontend_template.frontend_template import get_active_template

no_cache = 1

SPEND_LOGO = "/assets/spend/logo.svg"


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=" + quote(frappe.request.path)
		raise frappe.Redirect

	csrf_token = frappe.sessions.get_csrf_token()
	frappe.db.commit()  # nosemgrep
	context.boot = {
		"csrf_token": csrf_token,
		"site_name": frappe.local.site,
		"user": frappe.session.user,
		**get_logos(),
		"theme": get_active_template(),
	}


def get_logos():
	"""The tab icon and the sidebar logo from Frappe's logo settings, or the Spend logo."""
	favicon = frappe.get_website_settings("favicon")
	# same order as frappe's get_app_logo, without its fallback to the app_logo_url hooks
	app_logo = frappe.get_website_settings("app_logo") or frappe.get_cached_value(
		"Navbar Settings", "Navbar Settings", "app_logo"
	)
	return {
		"favicon": favicon if favicon and favicon != "attach_files:" else SPEND_LOGO,
		"app_logo": app_logo or SPEND_LOGO,
	}
