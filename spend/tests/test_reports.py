# Copyright (c) 2026, Trojan IT Solutions and Contributors
# See license.txt

"""Every report is checked against figures produced by real postings."""

import frappe

from spend.spend.depreciation import post_due_depreciation
from spend.assets.report.asset_book_value.asset_book_value import execute as asset_book_value
from spend.assets.report.asset_depreciation_schedule_report.asset_depreciation_schedule_report import (
	execute as depreciation_schedule_report,
)
from spend.assets.report.asset_register.asset_register import execute as asset_register
from spend.budgeting.report.budget_utilization.budget_utilization import execute as budget_utilization
from spend.budgeting.report.budget_vs_actual.budget_vs_actual import execute as budget_vs_actual
from spend.accounts.report.chart_of_accounts.chart_of_accounts import execute as chart_of_accounts
from spend.accounts.report.cost_center_wise_spending.cost_center_wise_spending import (
	execute as cost_center_spending,
)
from spend.assets.report.depreciation_due.depreciation_due import execute as depreciation_due
from spend.accounts.report.general_ledger.general_ledger import execute as general_ledger
from spend.projects.report.project_spend.project_spend import execute as project_spend
from spend.purchasing.report.supplier_outstanding.supplier_outstanding import execute as supplier_outstanding
from spend.tests.utils import (
	TEST_COMPANY,
	SpendTestCase,
	account,
	ensure_fiscal_year,
	make_asset,
	make_cost_center,
	make_journal_entry,
	make_project,
	make_purchase_invoice,
	make_supplier_payment,
)


class TestSpendReports(SpendTestCase):
	def setUp(self):
		super().setUp()
		self.fy = ensure_fiscal_year(2025)
		self.asset = make_asset()  # 120000, 12 x 10000 monthly from 2025-01-31
		post_due_depreciation(asset=self.asset.name, date="2025-03-31")

	def find(self, data, **match):
		return next(row for row in data if all(row.get(k) == v for k, v in match.items()))

	def test_asset_register(self):
		_, data, _, chart, summary = asset_register({"company": TEST_COMPANY, "as_on_date": "2025-12-31"})
		row = self.find(data, asset=self.asset.name)
		self.assertEqual(row.accumulated_depreciation, 30000)
		self.assertEqual(row.book_value, 90000)
		self.assertEqual(row.status, "Partially Depreciated")
		self.assertTrue(chart)
		self.assertEqual(self.find(summary, label="Book Value")["value"], 90000)

	def test_asset_register_as_on_date(self):
		_, data, *_ = asset_register({"company": TEST_COMPANY, "as_on_date": "2025-02-15"})
		self.assertEqual(self.find(data, asset=self.asset.name).accumulated_depreciation, 10000)

	def test_depreciation_schedule_report(self):
		_, data = depreciation_schedule_report({"company": TEST_COMPANY, "asset": self.asset.name})
		self.assertEqual(len(data), 12)
		self.assertEqual([d.posting_status for d in data[:3]], ["Posted"] * 3)
		_, unposted = depreciation_schedule_report(
			{"company": TEST_COMPANY, "asset": self.asset.name, "posting_status": "Not Posted"}
		)
		self.assertEqual(len(unposted), 9)

	def test_depreciation_due(self):
		_, data, _, _, _summary = depreciation_due({"company": TEST_COMPANY, "as_on_date": "2025-06-30"})
		rows = [d for d in data if d.asset == self.asset.name]
		self.assertEqual(len(rows), 3)  # Apr, May, Jun
		self.assertEqual(rows[0].days_overdue, 61)
		post_due_depreciation(asset=self.asset.name, date="2025-06-30")
		_, data, *_ = depreciation_due({"company": TEST_COMPANY, "as_on_date": "2025-06-30"})
		self.assertFalse([d for d in data if d.asset == self.asset.name])

	def test_asset_book_value_from_ledger(self):
		_, data, *_ = asset_book_value({"company": TEST_COMPANY, "as_on_date": "2025-03-31"})
		row = self.find(data, asset=self.asset.name)
		self.assertEqual(row.gross_value, 120000)
		self.assertEqual(row.book_value, 90000)
		self.assertEqual(row.depreciated_percent, 25)

	def test_budget_reports(self):
		budget = frappe.get_doc(
			{
				"doctype": "Budget",
				"company": TEST_COMPANY,
				"fiscal_year": self.fy,
				"cost_center": account("Main"),
				"budget_period": "Monthly",
				"accounts": [
					{"account": account("Depreciation"), "budget_amount": 100000},
					{"account": account("Office Rent"), "budget_amount": 24000},
				],
			}
		).insert()
		budget.submit()
		make_journal_entry(account("Office Rent"), account("Cash"), 6000, "2025-02-10", account("Main"))

		_, data, _, chart = budget_vs_actual({"company": TEST_COMPANY, "fiscal_year": self.fy})
		main = account("Main")  # other budgets, like the one test projects share, are listed too
		self.assertEqual(self.find(data, account=account("Depreciation"), cost_center=main)["actual"], 30000)
		rent = self.find(data, account=account("Office Rent"), cost_center=main)
		self.assertEqual((rent["actual"], rent["remaining"], rent["utilization"]), (6000, 18000, 25))
		self.assertTrue(chart)

		_, monthly, *_ = budget_vs_actual(
			{"company": TEST_COMPANY, "fiscal_year": self.fy, "period": "Monthly"}
		)
		feb_rent = self.find(monthly, account=account("Office Rent"), period="Feb 2025", cost_center=main)
		self.assertEqual(
			(feb_rent["budget_amount"], feb_rent["actual"], feb_rent["utilization"]), (2000, 6000, 300)
		)

		_, util, _, _, _summary = budget_utilization({"company": TEST_COMPANY, "fiscal_year": self.fy})
		row = self.find(util, budget=budget.name)
		self.assertEqual((row["allocated"], row["actual"]), (124000, 36000))
		self.assertEqual(row["utilization_status"], "On Track")

	def test_cost_center_wise_spending(self):
		ops = make_cost_center("Operations", is_group=1)
		it = make_cost_center("IT", parent=ops)
		make_journal_entry(account("Software Subscriptions"), account("Cash"), 5000, "2025-05-01", it)
		_, data, *_ = cost_center_spending(
			{"company": TEST_COMPANY, "from_date": "2025-01-01", "to_date": "2025-12-31"}
		)
		self.assertEqual(self.find(data, name=it)["spending"], 5000)
		self.assertEqual(self.find(data, name=ops)["spending"], 5000)
		self.assertEqual(self.find(data, name=account("Main"))["spending"], 30000)  # depreciation
		root = self.find(data, name=f"{TEST_COMPANY} - _TSC")
		self.assertEqual(root["spending"], 35000)
		self.assertEqual(root["indent"], 0)
		self.assertEqual(self.find(data, name=it)["indent"], 2)

	def test_chart_of_accounts_balances(self):
		_, data = chart_of_accounts({"company": TEST_COMPANY, "as_on_date": "2025-12-31"})
		self.assertEqual(self.find(data, account=account("Accumulated Depreciation"))["balance"], -30000)
		self.assertEqual(self.find(data, account=account("Office Equipment"))["balance"], 120000)
		self.assertEqual(self.find(data, account=account("Fixed Assets"))["balance"], 90000)
		self.assertEqual(self.find(data, account=account("Expenses"))["balance"], 30000)
		# whole ledger balances
		roots = [d for d in data if not d["parent_account"]]
		self.assertEqual(sum(d["balance"] for d in roots), 0)

	def test_general_ledger_balances(self):
		cash = account("Cash")
		make_journal_entry(account("Utilities"), cash, 100, "2025-03-10")
		make_journal_entry(account("Utilities"), cash, 40, "2025-05-02")
		make_journal_entry(account("Utilities"), cash, 25, "2025-05-20")
		make_journal_entry(account("Utilities"), cash, 999, "2025-05-21").cancel()

		filters = {"company": TEST_COMPANY, "from_date": "2025-05-01", "to_date": "2025-05-31"}
		_columns, data, _msg, _chart, summary = general_ledger({**filters, "account": account("Utilities")})
		closing, total, *rows, opening = data
		self.assertEqual((opening["debit"], opening["balance"]), (100, 100))
		self.assertEqual([r["balance"] for r in rows], [165, 140])
		self.assertEqual(total["debit"], 65)
		self.assertEqual((closing["debit"], closing["balance"]), (165, 165))
		self.assertEqual(summary[0]["value"], 65)

		# grouped: each account has its own opening, rows and closing, and the ledger balances
		_columns, data, *_rest = general_ledger({**filters, "group_by_account": 1})
		closings = [d for d in data if d["account"].startswith("Closing")]
		self.assertIn(165, [d["balance"] for d in closings])
		self.assertEqual(sum(d["balance"] for d in closings), 0)

	def test_supplier_outstanding_ageing(self):
		not_due = make_purchase_invoice([("Office Rent", 1000)], due_date="2025-07-10")
		overdue_20 = make_purchase_invoice([("Utilities", 2000)], due_date="2025-06-10")
		overdue_100 = make_purchase_invoice(
			[("Salaries", 3000)], posting_date="2025-02-01", due_date="2025-02-20"
		)
		make_supplier_payment([(overdue_20.name, 500)], posting_date="2025-06-15")
		cancelled = make_purchase_invoice([("Travel Expenses", 9999)])
		cancelled.cancel()
		self.assertTrue(not_due and overdue_100)

		_columns, data, _msg, chart, summary = supplier_outstanding(
			{"company": TEST_COMPANY, "as_on_date": "2025-06-30"}
		)
		row = self.find(data, supplier="_Test Supplier")
		self.assertEqual(row["invoiced"], 6000)
		self.assertEqual(row["paid"], 500)
		self.assertEqual(row["outstanding"], 5500)
		self.assertEqual(row["bills"], 3)
		self.assertEqual(row["not_due"], 1000)
		self.assertEqual(row["range_1"], 1500)
		self.assertEqual(row["range_4"], 3000)
		self.assertEqual(summary[1]["value"], 4500)
		self.assertEqual(chart["data"]["datasets"][0]["values"], [1000, 1500, 0, 0, 3000])

		# as on an earlier date, later bills and payments are left out
		_columns, data, *_rest = supplier_outstanding({"company": TEST_COMPANY, "as_on_date": "2025-02-28"})
		self.assertEqual(self.find(data, supplier="_Test Supplier")["outstanding"], 3000)

	def test_project_spend(self):
		project = make_project(budget=10000)
		idle = make_project("_Test Idle Project")
		invoice = make_purchase_invoice([("Office Rent", 6000), ("Utilities", 1000)], project=project.name)
		make_supplier_payment([(invoice.name, 4000)])

		_columns, data, _msg, chart, summary = project_spend({"company": TEST_COMPANY})
		row = self.find(data, name=project.name)
		self.assertEqual((row["spent"], row["remaining"], row["utilization"]), (7000, 3000, 70))
		self.assertEqual((row["billed"], row["paid"], row["outstanding"]), (7000, 4000, 3000))
		self.assertEqual(self.find(data, name=idle.name)["spent"], 0)
		self.assertIsNone(self.find(data, name=idle.name)["utilization"])
		self.assertEqual(chart["data"]["labels"], ["_Test Project"])
		self.assertEqual(summary[3]["value"], 0)
