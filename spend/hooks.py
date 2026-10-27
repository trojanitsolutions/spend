app_name = "spend"
app_title = "spend"
app_publisher = "Trojan IT Solutions"
app_description = "spend"
app_email = "dev3@trojanitsolutions.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
add_to_apps_screen = [
	{
		"name": "spend",
		"logo": "/assets/spend/logo.svg",
		"title": "Spend",
		"route": "/spend",
		"has_permission": "spend.api.has_app_permission",
	}
]

# The dock, the rail down the left of the desk, is a document rather than a hook. Author it in
# Manage Dock on a developer-mode site and press Export to App, and it is written to
# `spend/dock/spend/spend.json` for git to carry. An app that ships none has no
# rail: its sidebar gets a switcher in the header instead.
#
# A companion app, one that extends a host app rather than standing on its own, says so with
# `mount_on` on that same record, and its entries are appended to the host's rail. Mounting keeps
# the companion off the apps screen, so it takes precedence over any add_to_apps_screen above.

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/spend/css/spend.css"
# app_include_js = "/assets/spend/js/spend.js"

# include js, css files in header of web template
# web_include_css = "/assets/spend/css/spend.css"
# web_include_js = "/assets/spend/js/spend.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "spend/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_kanban_js = {"doctype" : "public/js/doctype_kanban.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "spend/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# serve the frappe-ui frontend (frontend/) for every path under /spend
website_route_rules = [
	{"from_route": "/spend/<path:app_path>", "to_route": "spend"},
]

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "spend.utils.jinja_methods",
# 	"filters": "spend.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "spend.install.before_install"
after_install = "spend.spend.setup.after_install"
# the workflow fixtures are imported after install and on every migrate; these put back
# the approval switches from Spend Settings over them
after_sync = "spend.spend.approval.apply_settings"
after_migrate = "spend.spend.approval.apply_settings"

# Uninstallation
# ------------

# before_uninstall = "spend.uninstall.before_uninstall"
# after_uninstall = "spend.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "spend.utils.before_app_install"
# after_app_install = "spend.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "spend.utils.before_app_uninstall"
# after_app_uninstall = "spend.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "spend.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "spend.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["spend.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

scheduler_events = {
	"daily": [
		"spend.spend.depreciation.post_depreciation_entries_daily",
		"spend.spend.doctype.purchase_invoice.purchase_invoice.update_overdue_invoices",
		"spend.spend.doctype.recurring_payment.recurring_payment.post_recurring_payments_daily",
		"spend.spend.notifications.notify_bills_due",
		"spend.spend.doctype.task.task.set_tasks_as_overdue",
	],
}

doc_events = {
	doctype: {
		"on_cancel": "spend.spend.approval.set_cancelled_state",
		"on_change": "spend.spend.notifications.on_approval_change",
	}
	for doctype in (
		"Purchase Invoice",
		"Supplier Payment",
		"Journal Entry",
		"Recurring Payment",
		"Budget",
		"Project",
	)
}

# The approval workflows ship as fixtures. After changing them on a developer-mode site, run
# `bench --site <site> export-fixtures --app spend`.
APPROVAL_WORKFLOWS = [
	f"{doctype} Approval"
	for doctype in (
		"Purchase Invoice",
		"Supplier Payment",
		"Journal Entry",
		"Recurring Payment",
		"Budget",
		"Project",
	)
]
fixtures = [
	{
		"dt": "Workflow State",
		"filters": [
			[
				"name",
				"in",
				[
					"Draft",
					"Pending Manager Approval",
					"Pending GM Approval",
					"Approved",
					"Rejected",
					"Cancelled",
				],
			]
		],
	},
	{
		"dt": "Workflow Action Master",
		"filters": [["name", "in", ["Send for Approval", "Approve", "Reject", "Resubmit", "Revise"]]],
	},
	{"dt": "Workflow", "filters": [["name", "in", APPROVAL_WORKFLOWS]]},
]

# Spend sends these by email itself, when Spend Settings allows it
notification_skip_email_types = ["Approval", "Budget Alert", "Bill Reminder", "Recurring Payment"]

# scheduler_events = {
# 	"all": [
# 		"spend.tasks.all"
# 	],
# 	"daily": [
# 		"spend.tasks.daily"
# 	],
# 	"hourly": [
# 		"spend.tasks.hourly"
# 	],
# 	"weekly": [
# 		"spend.tasks.weekly"
# 	],
# 	"monthly": [
# 		"spend.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "spend.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "spend.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "spend.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "spend.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["spend.utils.before_request"]
# after_request = ["spend.utils.after_request"]

# Job Events
# ----------
# before_job = ["spend.utils.before_job"]
# after_job = ["spend.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"spend.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
