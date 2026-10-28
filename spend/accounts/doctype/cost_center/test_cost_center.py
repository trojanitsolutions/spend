# Copyright (c) 2026, Trojan IT Solutions and Contributors
# See license.txt

import frappe

from spend.spend.accounting import get_balance
from spend.tests.utils import (
	SpendTestCase,
	account,
	make_company,
	make_cost_center,
	make_journal_entry,
	setup_test_data,
)

IGNORE_TEST_RECORD_DEPENDENCIES = ["Company", "Cost Center"]


class IntegrationTestCostCenter(SpendTestCase):
	def test_hierarchy_rollup(self):
		ops = make_cost_center("Operations", is_group=1)
		it = make_cost_center("IT", parent=ops)
		hr = make_cost_center("HR", parent=ops)
		make_journal_entry(account("Software Subscriptions"), account("Cash"), 300, "2025-04-01", it)
		make_journal_entry(account("Salaries"), account("Cash"), 700, "2025-04-01", hr)
		self.assertEqual(get_balance(cost_center=it), 300)
		self.assertEqual(get_balance(cost_center=ops), 1000)

	def test_cannot_post_to_group_cost_center(self):
		ops = make_cost_center("Operations", is_group=1)
		self.assertRaises(
			frappe.ValidationError,
			make_journal_entry,
			account("Salaries"),
			account("Cash"),
			10,
			"2025-04-01",
			ops,
		)

	def test_parent_must_belong_to_same_company(self):
		make_company("_Test Spend Company 2", "_TS2")
		cc = frappe.get_doc(
			{
				"doctype": "Cost Center",
				"cost_center_name": "Stray",
				"company": "_Test Spend Company 2",
				"parent_cost_center": "_Test Spend Company - _TSC",
			}
		)
		self.assertRaises(frappe.ValidationError, cc.insert)
