# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

CACHE_KEY = "spend_frontend_template"
DEFAULT_TEMPLATE = "Spend Default"

# white main panel; page bars, filters and tables sit in cards with a blue-tinted edge
CARDS_CSS = """:root {
	--canvas: #ffffff;
	--accent-ink: #1d4ed8;
}
.card,
main > * > .data-table {
	border-color: #dbe4f3;
	box-shadow: 0 1px 3px rgb(30 64 175 / 0.08), 0 1px 2px rgb(30 64 175 / 0.04);
}
main .bar-glass {
	margin: 1rem 1rem 1rem;
	border: 1px solid #dbe4f3;
	border-radius: 1rem;
	box-shadow: 0 1px 3px rgb(30 64 175 / 0.08);
}
main > * > .flex.flex-wrap.items-end.gap-3:not(.bar-glass) {
	margin: 0 1rem 1rem;
	padding: 1rem;
	border: 1px solid #dbe4f3;
	border-radius: 1rem;
	background: #ffffff;
	box-shadow: 0 1px 3px rgb(30 64 175 / 0.08);
}
@media (min-width: 640px) {
	main .bar-glass,
	main > * > .flex.flex-wrap.items-end.gap-3:not(.bar-glass) {
		margin-left: 1.5rem;
		margin-right: 1.5rem;
	}
}
"""

# fields the /spend app reads
THEME_FIELDS = (
	"name",
	"app_title",
	"app_logo",
	"favicon",
	"color_mode",
	"primary_color",
	"sidebar_color",
	"font_family",
	"corner_style",
	"density",
	"custom_css",
)

# standard looks besides the default, created once on install and migrate
STANDARD_TEMPLATES = (
	{
		"template_name": "Blue Sidebar",
		"description": "A blue sidebar with white text, a white main panel and all content in cards.",
		"color_mode": "Light",
		"primary_color": "#2563eb",
		"sidebar_color": "#1e40af",
		"corner_style": "Rounded",
		"custom_css": CARDS_CSS,
	},
	{
		"template_name": "Navy Sidebar",
		"description": "A dark navy sidebar with white text, a white main panel and all content in cards.",
		"color_mode": "Light",
		"primary_color": "#1d4ed8",
		"sidebar_color": "#0f1a36",
		"corner_style": "Rounded",
		"custom_css": CARDS_CSS,
	},
)


class FrontendTemplate(Document):
	def validate(self):
		if not self.is_active and self.has_value_changed("is_active") and not self.is_new():
			frappe.throw(_("Activate another template instead; one template must stay active"))

	def on_update(self):
		if self.is_active:
			frappe.db.set_value(
				"Frontend Template", {"name": ("!=", self.name), "is_active": 1}, "is_active", 0
			)
		frappe.cache.delete_value(CACHE_KEY)

	def on_trash(self):
		if self.is_standard:
			frappe.throw(_("The standard template {0} cannot be deleted").format(self.name))
		if self.is_active:
			frappe.throw(_("Activate another template before deleting {0}").format(self.name))
		frappe.cache.delete_value(CACHE_KEY)

	def after_rename(self, old, new, merge=False):
		frappe.cache.delete_value(CACHE_KEY)


def get_active_template() -> dict:
	"""The active template's theme fields, or an empty dict when there is none."""
	template = frappe.cache.get_value(CACHE_KEY)
	if template is None:
		template = (
			frappe.db.get_value("Frontend Template", {"is_active": 1}, THEME_FIELDS, as_dict=True) or {}
		)
		frappe.cache.set_value(CACHE_KEY, template)
	return template


def create_default_template():
	"""The standard templates: the look Spend was built with, then the sidebar looks."""
	if not frappe.db.exists("Frontend Template", DEFAULT_TEMPLATE):
		frappe.get_doc(
			{
				"doctype": "Frontend Template",
				"template_name": DEFAULT_TEMPLATE,
				"is_standard": 1,
				"is_active": not frappe.db.exists("Frontend Template", {"is_active": 1}),
				"description": "The standard Spend look: light theme, gray accents and the Inter font.",
			}
		).insert(ignore_permissions=True)

	for template in STANDARD_TEMPLATES:
		if not frappe.db.exists("Frontend Template", template["template_name"]):
			frappe.get_doc({"doctype": "Frontend Template", "is_standard": 1, **template}).insert(
				ignore_permissions=True
			)
