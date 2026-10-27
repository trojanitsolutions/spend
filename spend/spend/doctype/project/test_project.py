# Copyright (c) 2026, Trojan IT Solutions and Contributors
# See license.txt

import frappe

from spend.spend.accounting import InactiveProjectError, get_balance
from spend.spend.doctype.budget.budget import BudgetExceededError
from spend.spend.doctype.budget.test_budget import make_budget
from spend.spend.doctype.project.project import (
	get_budget_allocation,
	get_project_spent,
	get_project_summary,
)
from spend.tests.utils import (
	SpendTestCase,
	account,
	make_company,
	make_cost_center,
	make_journal_entry,
	make_project,
	make_purchase_invoice,
)

IGNORE_TEST_RECORD_DEPENDENCIES = ["Company", "Account", "Cost Center", "Fiscal Year"]


class IntegrationTestProject(SpendTestCase):
	def test_new_project_has_no_spend(self):
		project = make_project(budget=10000)
		summary = get_project_summary(project.name)
		self.assertEqual((summary["spent"], summary["remaining"], summary["billed"]), (0, 10000, 0))

	def test_bill_lines_carry_project_to_ledger(self):
		project = make_project()
		invoice = make_purchase_invoice([("Office Rent", 3000), ("Utilities", 500)], project=project.name)
		self.assertEqual({item.project for item in invoice.items}, {project.name})
		rows = frappe.get_all("GL Entry", {"voucher_no": invoice.name}, ["account", "project"])
		self.assertTrue(all(row.project == project.name for row in rows))
		self.assertEqual(get_project_spent(project.name), 3500)
		self.assertEqual(get_balance(project=project.name, account=account("Creditors")), -3500)

	def test_line_project_overrides_header(self):
		first, second = make_project("_Test Project A"), make_project("_Test Project B")
		invoice = make_purchase_invoice(
			[("Office Rent", 1000), ("Utilities", 200, second.name)], project=first.name
		)
		self.assertEqual(get_project_spent(first.name), 1000)
		self.assertEqual(get_project_spent(second.name), 200)
		payable = frappe.db.get_value(
			"GL Entry", {"voucher_no": invoice.name, "account": account("Creditors")}, "project"
		)
		self.assertIsNone(payable)

	def test_stop_budget_blocks_and_warn_allows(self):
		stop = make_project("_Test Stop", budget=5000, action="Stop")
		make_purchase_invoice([("Office Rent", 4000)], project=stop.name)
		with self.assertRaises(BudgetExceededError):
			make_purchase_invoice([("Office Rent", 1500)], project=stop.name)

		warn = make_project("_Test Warn", budget=5000, action="Warn")
		make_purchase_invoice([("Office Rent", 6000)], project=warn.name)
		self.assertEqual(get_project_spent(warn.name), 6000)

	def test_account_limit_blocks_within_total(self):
		project = make_project(budget=10000, action="Stop", accounts=[("Utilities", 1000)])
		make_purchase_invoice([("Office Rent", 5000)], project=project.name)
		with self.assertRaises(BudgetExceededError):
			make_purchase_invoice([("Utilities", 1200)], project=project.name)
		self.assertEqual(get_project_summary(project.name)["accounts"][0]["actual"], 0)

	def test_journal_entry_row_counts_towards_spend(self):
		project = make_project(budget=1000, action="Stop")
		je = make_journal_entry(account("Office Rent"), account("Cash"), 400, "2025-03-01", submit=False)
		je.accounts[0].project = project.name
		je.save()
		je.submit()
		self.assertEqual(get_project_spent(project.name), 400)
		je.cancel()
		self.assertEqual(get_project_spent(project.name), 0)

	def test_closed_project_rejects_new_bills(self):
		project = make_project()
		project.db_set("status", "Completed")
		with self.assertRaises(InactiveProjectError):
			make_purchase_invoice(project=project.name)

	def test_project_of_another_company_is_rejected(self):
		other = make_company("_Test Spend Company 2", "_TS2")
		project = make_project(company=other.name)
		with self.assertRaises(frappe.ValidationError):
			make_purchase_invoice(project=project.name)

	def test_account_limits_cannot_exceed_total(self):
		with self.assertRaises(frappe.ValidationError):
			make_project(budget=1000, accounts=[("Office Rent", 800), ("Utilities", 300)])
		with self.assertRaises(frappe.ValidationError):
			make_project(accounts=[("Cash", 100)])

	def test_used_project_cannot_be_deleted(self):
		project = make_project()
		make_purchase_invoice(project=project.name)
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("Project", project.name)

	def test_projects_share_their_budget(self):
		budget = make_budget({account("Office Rent"): 10000, account("Utilities"): 2000})
		first = make_project(
			"_Test Project A", budget=6000, accounts=[("Office Rent", 6000)], budget_doc=budget.name
		)
		self.assertEqual(first.cost_center, account("Main"))

		with self.assertRaisesRegex(frappe.ValidationError, "4,000"):
			make_project(
				"_Test Project B", budget=5000, accounts=[("Office Rent", 5000)], budget_doc=budget.name
			)
		second = make_project(
			"_Test Project B", budget=4000, accounts=[("Office Rent", 4000)], budget_doc=budget.name
		)

		allocation = get_budget_allocation(budget.name)
		self.assertEqual(allocation["held"], 10000)
		self.assertEqual(
			{r["account"]: r["free"] for r in allocation["accounts"]},
			{account("Office Rent"): 0, account("Utilities"): 2000},
		)

		second.db_set("status", "Cancelled")
		make_project("_Test Project C", budget=3000, accounts=[("Office Rent", 3000)], budget_doc=budget.name)

	def test_share_stays_within_the_budget(self):
		budget = make_budget({account("Office Rent"): 10000})
		with self.assertRaisesRegex(frappe.ValidationError, "is not on Budget"):
			make_project(accounts=[("Utilities", 100)], budget_doc=budget.name)
		elsewhere = make_cost_center("_Test Elsewhere")
		with self.assertRaisesRegex(frappe.ValidationError, "is not under"):
			make_project(budget=100, cost_center=elsewhere, budget_doc=budget.name)

		budget.cancel()
		with self.assertRaisesRegex(frappe.ValidationError, "not submitted"):
			make_project(budget=100, budget_doc=budget.name)
