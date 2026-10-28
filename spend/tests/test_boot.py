# Copyright (c) 2026, Trojan IT Solutions and Contributors
# See license.txt

import frappe
from frappe import _dict

from spend.api import get_boot, get_dashboard
from spend.spend.boot import filter_sidebar
from spend.tests.utils import SpendTestCase, make_user

ACCOUNTS_USER = "_spend_boot_user@example.com"
BLOCKED_USER = "_spend_boot_blocked@example.com"
GM = "_spend_boot_gm@example.com"

ASSET_REPORTS = {"Asset Register", "Asset Depreciation Schedule Report", "Depreciation Due", "Asset Book Value"}


class TestBoot(SpendTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_user(ACCOUNTS_USER, ["Accounts Manager"])
		make_user(GM, ["General Manager"])
		make_user(BLOCKED_USER, ["Accounts Manager"])
		user = frappe.get_doc("User", BLOCKED_USER)
		user.set("block_modules", [{"module": "Assets"}])
		user.save(ignore_permissions=True)

	def setUp(self):
		super().setUp()
		self.addCleanup(frappe.set_user, "Administrator")

	def boot_as(self, user):
		frappe.set_user(user)
		return get_boot()

	def test_general_manager_sees_only_permitted_doctypes(self):
		boot = self.boot_as(GM)
		self.assertFalse(boot["permissions"]["Account"]["read"])
		self.assertFalse(boot["permissions"]["Asset"]["read"])
		self.assertTrue(boot["permissions"]["Budget"]["read"])
		self.assertTrue(boot["permissions"]["Purchase Invoice"]["read"])
		self.assertEqual(boot["reports"], [])

	def test_general_manager_dashboard_shows_only_permitted_sections(self):
		frappe.set_user(GM)
		data = get_dashboard(self.company.name)
		for section in ("assets", "depreciation_due", "spending_trend", "top_cost_centers"):
			self.assertIsNone(data[section], section)
		for section in ("budget", "payables", "projects", "recent_entries"):
			self.assertIsNotNone(data[section], section)

	def test_accounts_user_sees_every_module(self):
		boot = self.boot_as(ACCOUNTS_USER)
		self.assertTrue(all(perms["read"] for perms in boot["permissions"].values()))
		reports = frappe.get_all("Report", filters={"module": ("in", frappe.get_module_list("spend"))}, pluck="name")
		self.assertEqual(set(boot["reports"]), set(reports))
		self.assertTrue(ASSET_REPORTS <= set(boot["reports"]))

	def test_blocked_module_is_hidden(self):
		boot = self.boot_as(BLOCKED_USER)
		self.assertFalse(boot["permissions"]["Asset"]["read"])
		self.assertTrue(boot["permissions"]["Budget"]["read"])
		self.assertFalse(ASSET_REPORTS & set(boot["reports"]))
		self.assertIn("Budget vs Actual", boot["reports"])

	def test_sidebar_drops_blocked_module_links(self):
		items = [
			{"type": "Section Break", "label": "Assets"},
			{"type": "Link", "link_type": "DocType", "link_to": "Asset", "child": 1},
			{"type": "Link", "link_type": "Report", "link_to": "Asset Register", "child": 1},
			{"type": "Link", "link_type": "DocType", "link_to": "Budget", "child": 1},
		]
		bootinfo = _dict(module_sidebars={"Spend": {"items": list(items)}})

		frappe.set_user(BLOCKED_USER)
		filter_sidebar(bootinfo)
		links = [i.get("link_to") for i in bootinfo.module_sidebars["Spend"]["items"]]
		self.assertEqual(links, [None, "Budget"])

		frappe.set_user(ACCOUNTS_USER)
		bootinfo = _dict(module_sidebars={"Spend": {"items": list(items)}})
		filter_sidebar(bootinfo)
		self.assertEqual(len(bootinfo.module_sidebars["Spend"]["items"]), 4)
