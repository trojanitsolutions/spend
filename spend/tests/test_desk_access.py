# Copyright (c) 2026, Trojan IT Solutions and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe import _dict
from werkzeug.routing import RequestRedirect

from spend.spend.desk_access import redirect_from_desk
from spend.tests.utils import SpendTestCase, make_user

STAFF = "_spend_desk_staff@example.com"
MANAGER = "_spend_desk_manager@example.com"


class TestDeskAccess(SpendTestCase):
	def visit(self, user, path):
		frappe.set_user(user)
		self.addCleanup(frappe.set_user, "Administrator")
		with patch.object(frappe.local, "request", _dict(path=path), create=True):
			redirect_from_desk()

	def test_staff_are_sent_to_spend(self):
		make_user(STAFF, ["Accounts Manager"])
		for path in ("/desk", "/desk/journal-entry/JE-1", "/app", "/app/budget", "/apps"):
			with self.assertRaises(RequestRedirect) as caught:
				self.visit(STAFF, path)
			self.assertTrue(caught.exception.new_url.endswith("/spend"))

	def test_others_pass(self):
		make_user(STAFF, ["Accounts Manager"])
		make_user(MANAGER, ["System Manager"])
		self.visit(STAFF, "/spend/expenses")
		self.visit(STAFF, "/api/method/spend.api.get_boot")
		self.visit(STAFF, "/desktop-icons")
		self.visit(MANAGER, "/desk/journal-entry")
		self.visit("Administrator", "/app")
		self.visit("Guest", "/desk")
