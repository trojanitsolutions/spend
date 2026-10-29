# Copyright (c) 2026, Trojan IT Solutions and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from spend.spend.doctype.frontend_template.frontend_template import (
	DEFAULT_TEMPLATE,
	create_default_template,
	get_active_template,
)


class IntegrationTestFrontendTemplate(IntegrationTestCase):
	def setUp(self):
		frappe.db.savepoint("frontend_template_test")
		self.addCleanup(frappe.cache.delete_value, "spend_frontend_template")
		self.addCleanup(frappe.db.rollback, save_point="frontend_template_test")
		create_default_template()

	def make_template(self, name, **values):
		return frappe.get_doc({"doctype": "Frontend Template", "template_name": name, **values}).insert()

	def active(self):
		return frappe.get_all("Frontend Template", filters={"is_active": 1}, pluck="name")

	def test_only_one_template_is_active(self):
		self.make_template("_Test Ocean", is_active=1, primary_color="#0ea5e9")
		self.assertEqual(self.active(), ["_Test Ocean"])

		frappe.get_doc("Frontend Template", DEFAULT_TEMPLATE).update({"is_active": 1}).save()
		self.assertEqual(self.active(), [DEFAULT_TEMPLATE])

	def test_active_template_cannot_be_unchecked(self):
		default = frappe.get_doc("Frontend Template", DEFAULT_TEMPLATE)
		default.update({"is_active": 1}).save()
		default.is_active = 0
		self.assertRaises(frappe.ValidationError, default.save)

	def test_standard_and_active_templates_cannot_be_deleted(self):
		self.make_template("_Test Ocean", is_active=1)
		self.assertRaises(frappe.ValidationError, frappe.delete_doc, "Frontend Template", DEFAULT_TEMPLATE)
		self.assertRaises(frappe.ValidationError, frappe.delete_doc, "Frontend Template", "_Test Ocean")

	def test_active_template_cache_follows_changes(self):
		frappe.get_doc("Frontend Template", DEFAULT_TEMPLATE).update({"is_active": 1}).save()
		self.assertEqual(get_active_template()["name"], DEFAULT_TEMPLATE)

		self.make_template("_Test Ocean", is_active=1, app_title="Acme Spend")
		self.assertEqual(get_active_template()["app_title"], "Acme Spend")
