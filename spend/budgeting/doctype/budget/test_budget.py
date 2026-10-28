# Copyright (c) 2026, Trojan IT Solutions and Contributors
# See license.txt

import frappe

from spend.spend.amendment import get_amendment, get_versions
from spend.budgeting.doctype.budget.budget import BudgetExceededError, DuplicateBudgetError, get_budget_summary
from spend.projects.doctype.project.project import get_budget_allocation, search_booking_accounts
from spend.spend.accounting import BudgetAccountError
from spend.tests.utils import (
	TEST_COMPANY,
	SpendTestCase,
	account,
	close_open_budget,
	ensure_fiscal_year,
	make_cost_center,
	make_item,
	make_journal_entry,
	make_project,
	make_purchase_invoice,
	make_recurring_payment,
	make_supplier,
	setup_test_data,
)

IGNORE_TEST_RECORD_DEPENDENCIES = ["Company", "Account", "Cost Center", "Fiscal Year"]


def make_budget(accounts, cost_center=None, action="Warn", period="Annual", submit=True, **kw):
	budget = frappe.get_doc(
		{
			"doctype": "Budget",
			"company": TEST_COMPANY,
			"fiscal_year": ensure_fiscal_year(2025),
			"cost_center": cost_center or account("Main"),
			"budget_period": period,
			"action_if_exceeded": action,
			"accounts": [{"account": acc, "budget_amount": amt} for acc, amt in accounts.items()],
			**kw,
		}
	).insert()
	if submit:
		budget.submit()
	return budget


def amend(doctype, name, reason="Revised", **changes):
	doc = frappe.get_doc(get_amendment(doctype, name)["doc"])
	doc.update({"amendment_reason": reason, **changes})
	return doc


class IntegrationTestBudget(SpendTestCase):
	def test_budget_vs_actual_from_ledger(self):
		budget = make_budget({account("Office Rent"): 12000, account("Utilities"): 3000})
		make_journal_entry(account("Office Rent"), account("Cash"), 1000, "2025-02-01", account("Main"))
		make_journal_entry(account("Office Rent"), account("Cash"), 2000, "2025-03-01", account("Main"))
		cancelled = make_journal_entry(
			account("Utilities"), account("Cash"), 999, "2025-03-01", account("Main")
		)
		cancelled.cancel()

		summary = get_budget_summary(budget.name)
		rent = next(r for r in summary["rows"] if r["account"] == account("Office Rent"))
		utilities = next(r for r in summary["rows"] if r["account"] == account("Utilities"))
		self.assertEqual(budget.total_budget, 15000)
		self.assertEqual(rent["actual"], 3000)
		self.assertEqual(rent["remaining"], 9000)
		self.assertEqual(rent["utilization"], 25)
		self.assertEqual(utilities["actual"], 0)  # cancelled entries never count
		self.assertEqual(summary["utilization"], 20)

	def test_stop_blocks_and_warn_allows(self):
		make_budget({account("Office Rent"): 1000}, action="Stop")
		make_journal_entry(account("Office Rent"), account("Cash"), 900, "2025-02-01", account("Main"))
		self.assertRaises(
			BudgetExceededError,
			make_journal_entry,
			account("Office Rent"),
			account("Cash"),
			200,
			"2025-02-02",
			account("Main"),
		)
		make_budget({account("Utilities"): 100}, action="Warn")
		je = make_journal_entry(account("Utilities"), account("Cash"), 500, "2025-02-02", account("Main"))
		self.assertEqual(je.docstatus, 1)

	def test_parent_cost_center_budget_covers_children(self):
		ops = make_cost_center("Operations", is_group=1)
		it = make_cost_center("IT", parent=ops)
		make_budget({account("Software Subscriptions"): 500}, cost_center=ops, action="Stop")
		make_journal_entry(account("Software Subscriptions"), account("Cash"), 400, "2025-06-01", it)
		self.assertRaises(
			BudgetExceededError,
			make_journal_entry,
			account("Software Subscriptions"),
			account("Cash"),
			200,
			"2025-06-01",
			it,
		)

	def test_monthly_distribution_and_monthly_limit(self):
		budget = make_budget({account("Travel Expenses"): 12000}, action="Stop", period="Monthly")
		self.assertEqual(len(budget.monthly_distribution), 12)
		self.assertAlmostEqual(sum(r.percentage for r in budget.monthly_distribution), 100, places=2)
		make_journal_entry(account("Travel Expenses"), account("Cash"), 900, "2025-01-15", account("Main"))
		# 1000 per month: January would exceed, February is still free
		self.assertRaises(
			BudgetExceededError,
			make_journal_entry,
			account("Travel Expenses"),
			account("Cash"),
			200,
			"2025-01-20",
			account("Main"),
		)
		make_journal_entry(account("Travel Expenses"), account("Cash"), 200, "2025-02-01", account("Main"))
		jan = next(p for p in get_budget_summary(budget.name)["periods"] if p["period"] == "Jan 2025")
		self.assertEqual(jan["actual"], 900)
		self.assertEqual(jan["budget"], 1000)

	def test_distribution_must_total_100(self):
		budget = make_budget({account("Travel Expenses"): 12000}, period="Monthly", submit=False)
		budget.monthly_distribution[0].percentage = 50
		self.assertRaises(frappe.ValidationError, budget.save)

	def test_duplicate_budget_rejected(self):
		make_budget({account("Office Rent"): 1000})
		self.assertRaises(DuplicateBudgetError, make_budget, {account("Office Rent"): 500})

	def test_only_expense_ledgers_allowed(self):
		self.assertRaises(frappe.ValidationError, make_budget, {account("Sales"): 100}, submit=False)
		self.assertRaises(
			frappe.ValidationError, make_budget, {account("Indirect Expenses"): 100}, submit=False
		)

	def test_projects_move_to_the_approved_amendment(self):
		budget = make_budget({account("Office Rent"): 10000, account("Utilities"): 2000})
		project = make_project(budget=6000, accounts=[("Office Rent", 6000)], budget_doc=budget.name)
		other = make_project("_Test Other Project", budget=1000, budget_doc=budget.name)
		budget.cancel()

		smaller = amend("Budget", budget.name, accounts=[])
		smaller.append("accounts", {"account": account("Office Rent"), "budget_amount": 5000})
		smaller.insert()  # only warns while it is a draft
		with self.assertRaisesRegex(frappe.ValidationError, "_Test Project"):
			smaller.submit()
		self.assertEqual(frappe.db.get_value("Project", project.name, "budget"), budget.name)

		smaller.reload()
		smaller.accounts[0].budget_amount = 8000
		smaller.save()
		smaller.submit()
		self.assertEqual(frappe.db.get_value("Project", project.name, "budget"), smaller.name)
		# shared by two projects, so their shares stay
		self.assertEqual(frappe.db.get_value("Project", project.name, "budget_amount"), 6000)
		self.assertEqual(frappe.db.get_value("Project", other.name, "budget_amount"), 1000)

	def test_sole_project_takes_the_revised_amounts(self):
		budget = make_budget({account("Office Rent"): 10000, account("Utilities"): 2000})
		project = make_project(budget=6000, accounts=[("Office Rent", 6000)], budget_doc=budget.name)
		budget.cancel()

		amended = amend("Budget", budget.name, accounts=[])
		amended.append("accounts", {"account": account("Office Rent"), "budget_amount": 5000})
		amended.append("accounts", {"account": account("Travel Expenses"), "budget_amount": 500})
		amended.insert()
		amended.submit()  # below the old share, which the project gives up

		project.reload()
		self.assertEqual((project.budget, project.budget_amount), (amended.name, 5500))
		self.assertEqual(
			{r.account: r.budget_amount for r in project.budget_accounts},
			{account("Office Rent"): 5000, account("Travel Expenses"): 500},
		)
		self.assertTrue(
			frappe.db.exists(
				"Comment", {"reference_name": project.name, "content": ("like", "Share set to%")}
			)
		)

	def test_sole_project_recurring_payments_must_fit_the_revision(self):
		budget = make_budget({account("Office Rent"): 10000})
		project = make_project(budget=3000, accounts=[("Office Rent", 3000)], budget_doc=budget.name)
		make_recurring_payment(total=1200, project=project.name, cost_center=account("Main"))
		budget.cancel()

		smaller = amend("Budget", budget.name)
		smaller.accounts[0].budget_amount = 1000
		smaller.insert()
		with self.assertRaisesRegex(frappe.ValidationError, "_Test Rent"):
			smaller.submit()

		smaller.reload()
		smaller.accounts[0].budget_amount = 1200
		smaller.save()
		smaller.submit()
		self.assertEqual(frappe.db.get_value("Project", project.name, "budget_amount"), 1200)

	def test_recurring_payments_move_to_the_approved_amendment(self):
		budget = make_budget({account("Office Rent"): 10000})
		project = make_project(budget=3000, accounts=[("Office Rent", 3000)], budget_doc=budget.name)
		rent = make_recurring_payment(total=6000, budget=budget.name, cost_center=account("Main"))
		on_project = make_recurring_payment(total=1200, project=project.name, cost_center=account("Main"))
		budget.cancel()

		smaller = amend("Budget", budget.name)
		smaller.accounts[0].budget_amount = 8000
		smaller.insert()
		with self.assertRaisesRegex(frappe.ValidationError, rent.name):
			smaller.submit()  # the project holds 3,000 and the payment 6,000

		smaller.reload()
		smaller.accounts[0].budget_amount = 9000
		smaller.save()
		smaller.submit()
		for name in (rent.name, on_project.name):
			self.assertEqual(frappe.db.get_value("Recurring Payment", name, "budget"), smaller.name)

	def test_allocation_lists_what_recurring_payments_still_pay(self):
		budget = make_budget({account("Office Rent"): 10000})
		project = make_project(budget=3000, accounts=[("Office Rent", 3000)], budget_doc=budget.name)
		rent = make_recurring_payment(total=6000, budget=budget.name, cost_center=account("Main"))
		on_project = make_recurring_payment(total=1200, project=project.name, cost_center=account("Main"))
		frappe.db.set_value("Recurring Payment", rent.name, "paid_amount", 1000)

		allocation = get_budget_allocation(budget.name)
		rows = {r["name"]: r for r in allocation["recurring"]}
		self.assertEqual(rows[rent.name]["remaining"], 5000)
		self.assertTrue(rows[rent.name]["counted"])
		self.assertEqual(rows[on_project.name]["project_name"], project.project_name)
		self.assertFalse(rows[on_project.name]["counted"])
		self.assertEqual(rows[on_project.name]["remaining"], 0)  # its dates are past, so all of it is paid
		self.assertEqual(allocation["recurring_remaining"], 5000)
		self.assertEqual(allocation["held"], 9000)  # the project's payment is inside its share

	def test_cancel_and_amend_replaces_budget(self):
		budget = make_budget({account("Office Rent"): 1000, account("Utilities"): 500}, action="Stop")
		self.assertRaises(frappe.ValidationError, get_amendment, "Budget", budget.name)  # cancel first
		budget.cancel()

		self.assertRaises(frappe.ValidationError, amend("Budget", budget.name, reason="").insert)
		self.assertRaises(
			frappe.ValidationError,
			amend("Budget", budget.name, cost_center=make_cost_center("_Test Amend CC")).insert,
		)

		amended = amend("Budget", budget.name, accounts=[])
		amended.append("accounts", {"account": account("Office Rent"), "budget_amount": 2000})
		amended.append("accounts", {"account": account("Travel Expenses"), "budget_amount": 500})
		amended.insert()
		self.assertEqual(amended.name, f"{budget.name}-1")
		self.assertEqual(get_amendment("Budget", budget.name), {"existing": amended.name})

		amended.submit()
		self.assertRaises(frappe.ValidationError, get_amendment, "Budget", budget.name)
		# the new amounts apply: 1,500 rent was over the old Stop limit, utilities are no longer budgeted
		make_journal_entry(account("Office Rent"), account("Cash"), 1500, "2025-02-01", account("Main"))
		make_journal_entry(account("Utilities"), account("Cash"), 900, "2025-02-01", account("Main"))

		versions = get_versions("Budget", budget.name)
		self.assertEqual([v["name"] for v in versions], [budget.name, amended.name])
		self.assertEqual(versions[1]["net_change"], 1000)
		self.assertEqual(versions[1]["reason"], "Revised")
		self.assertEqual(
			{c["account"]: c["change"] for c in versions[1]["changes"]},
			{account("Office Rent"): 1000, account("Utilities"): -500, account("Travel Expenses"): 500},
		)

	def test_amendment_moves_money_and_changes_monthly_split(self):
		budget = make_budget(
			{account("Office Rent"): 1200, account("Utilities"): 1200}, period="Monthly", action="Stop"
		)
		budget.cancel()
		amended = amend("Budget", budget.name, action_if_exceeded="Warn")
		amended.accounts[0].budget_amount = 1800
		amended.accounts[1].budget_amount = 600
		first, second = amended.monthly_distribution[:2]
		second.percentage += first.percentage
		first.percentage = 0
		amended.insert()
		amended.submit()

		self.assertEqual(amended.monthly_distribution[0].percentage, 0)
		self.assertEqual(get_versions("Budget", amended.name)[-1]["net_change"], 0)

	def test_each_amendment_gets_the_next_name(self):
		budget = make_budget({account("Office Rent"): 1000})
		budget.cancel()
		first = amend("Budget", budget.name).insert()
		first.submit()
		first.cancel()
		second = amend("Budget", first.name, reason="Second change").insert()
		self.assertEqual(second.name, f"{budget.name}-2")
		self.assertEqual(len(get_versions("Budget", budget.name)), 3)


class IntegrationTestBudgetAccounts(SpendTestCase):
	"""Expense debits go only to accounts budgeted on their cost center (or project)."""

	def setUp(self):
		super().setUp()
		close_open_budget(2025)
		self.cost_center = make_cost_center("_Test Budgeted CC")
		make_budget({account("Office Rent"): 5000}, cost_center=self.cost_center)

	def test_debit_only_to_budgeted_accounts(self):
		with self.assertRaisesRegex(BudgetAccountError, "Use one of"):
			make_journal_entry(account("Utilities"), account("Cash"), 100, "2025-03-01", self.cost_center)
		make_journal_entry(account("Office Rent"), account("Cash"), 100, "2025-03-01", self.cost_center)
		# a credit to an expense account is not a spend
		make_journal_entry(account("Cash"), account("Utilities"), 100, "2025-03-01", self.cost_center)

	def test_cost_center_without_budget_books_no_expense(self):
		other = make_cost_center("_Test Unbudgeted CC")
		with self.assertRaisesRegex(BudgetAccountError, "no submitted Budget"):
			make_journal_entry(account("Office Rent"), account("Cash"), 100, "2025-03-01", other)

	def test_bill_line_takes_the_only_budgeted_account(self):
		bill = frappe.get_doc(
			{
				"doctype": "Purchase Invoice",
				"supplier": make_supplier().name,
				"company": TEST_COMPANY,
				"posting_date": "2025-03-01",
				"due_date": "2025-03-31",
				"cost_center": self.cost_center,
				"items": [{"item_code": make_item().name, "qty": 1, "rate": 100}],
			}
		).insert()
		self.assertEqual(bill.items[0].expense_account, account("Office Rent"))
		with self.assertRaises(BudgetAccountError):
			make_purchase_invoice([("Utilities", 100)], cost_center=self.cost_center)

	def test_account_search_shows_budgeted_expense_accounts(self):
		filters = {"company": TEST_COMPANY, "cost_center": self.cost_center, "posting_date": "2025-03-01"}
		search = lambda f: [r[0] for r in search_booking_accounts("Account", "", "name", 0, 500, f)]  # noqa: E731
		expense_only = search({**filters, "expense_only": 1})
		self.assertEqual(expense_only, [account("Office Rent")])
		journal = search(filters)
		self.assertIn(account("Office Rent"), journal)
		self.assertIn(account("Cash"), journal)
		self.assertNotIn(account("Utilities"), journal)


	def test_patch_logs_expenses_outside_the_cost_center_budget(self):
		from spend.patches.v0_1.align_project_budgets import report_unbudgeted_expenses

		entry = make_journal_entry(
			account("Office Rent"), account("Cash"), 100, "2025-03-01", self.cost_center
		)
		# booked before the check: the budget now has another account
		budget = frappe.db.get_value("Budget", {"cost_center": self.cost_center, "docstatus": 1})
		frappe.db.set_value(
			"Budget Account", {"parent": budget, "account": account("Office Rent")}, "account", account("Travel Expenses")
		)
		report_unbudgeted_expenses()
		log = frappe.db.get_value(
			"Error Log", {"method": "Expenses outside budgeted accounts"}, "error", order_by="creation desc"
		)
		self.assertIn(entry.name, log)
