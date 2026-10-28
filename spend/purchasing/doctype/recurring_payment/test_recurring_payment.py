# Copyright (c) 2026, Trojan IT Solutions and Contributors
# See license.txt

import frappe
from frappe.utils import add_months, getdate

from spend.spend.accounting import InactiveProjectError
from spend.spend.amendment import get_amendment
from spend.budgeting.doctype.budget.budget import BudgetExceededError
from spend.projects.doctype.project.project import get_budget_allocation, get_project_spent
from spend.purchasing.doctype.recurring_payment.recurring_payment import (
	RecurringPaymentError,
	get_payment_dates,
	get_recurring_room,
	make_payment_entries,
	post_recurring_payments_daily,
	preview_schedule,
	resume,
	split_amount,
	stop,
)
from spend.tests.utils import (
	SpendTestCase,
	account,
	get_project_budget,
	get_recurring_cost_center,
	make_company,
	make_cost_center,
	make_project,
	make_purchase_invoice,
	make_recurring_payment,
)

IGNORE_TEST_RECORD_DEPENDENCIES = ["Company", "Account", "Cost Center", "Fiscal Year"]


class UnitTestRecurringSchedule(SpendTestCase):
	def test_frequencies(self):
		self.assertEqual(len(get_payment_dates("2025-01-01", "2025-12-31", "Monthly")), 12)
		self.assertEqual(len(get_payment_dates("2025-01-01", "2025-12-31", "Quarterly")), 4)
		self.assertEqual(
			get_payment_dates("2025-04-01", "2028-03-31", "Yearly"),
			[getdate("2025-04-01"), getdate("2026-04-01"), getdate("2027-04-01")],
		)

	def test_month_end_start_keeps_month_ends(self):
		dates = get_payment_dates("2025-01-31", "2025-04-30", "Monthly")
		self.assertEqual([str(d) for d in dates], ["2025-01-31", "2025-02-28", "2025-03-31", "2025-04-30"])

	def test_split_puts_rounding_on_last_row(self):
		self.assertEqual(split_amount(1000, 3), [333.33, 333.33, 333.34])
		self.assertEqual(
			sum(r["amount"] for r in preview_schedule("2025-01-01", "2025-03-31", "Monthly", 100)), 100
		)


class IntegrationTestRecurringPayment(SpendTestCase):
	def test_draft_builds_schedule(self):
		doc = make_recurring_payment(total=3000, frequency="Quarterly", submit=False)
		self.assertEqual([r.amount for r in doc.schedule], [750, 750, 750, 750])
		self.assertEqual(doc.status, "Draft")
		self.assertEqual(doc.cost_center, get_recurring_cost_center())

	def test_custom_dates_split_or_must_match_total(self):
		dates = [
			{"payment_date": "2025-06-10"},
			{"payment_date": "2025-02-05"},
			{"payment_date": "2025-09-01"},
		]
		doc = make_recurring_payment(total=1000, frequency="Custom", schedule=dates, submit=False)
		self.assertEqual(
			[str(r.payment_date) for r in doc.schedule], ["2025-02-05", "2025-06-10", "2025-09-01"]
		)
		self.assertEqual([r.amount for r in doc.schedule], [333.33, 333.33, 333.34])

		doc.schedule[0].amount, doc.schedule[1].amount, doc.schedule[2].amount = 500, 200, 300
		doc.save()
		self.assertEqual([r.amount for r in doc.schedule], [500, 200, 300])
		doc.schedule[2].amount = 100
		with self.assertRaises(RecurringPaymentError):
			doc.save()

	def test_custom_dates_outside_range_or_repeated(self):
		for dates in (["2026-02-01"], ["2025-03-01", "2025-03-01"]):
			with self.assertRaises(RecurringPaymentError):
				make_recurring_payment(
					frequency="Custom", schedule=[{"payment_date": d} for d in dates], submit=False
				)

	def test_submit_posts_due_rows_with_project(self):
		project = make_project(budget=100000, budget_doc=get_project_budget(year=2029))
		doc = make_recurring_payment(
			total=1200, from_date="2029-01-01", to_date="2029-12-31", project=project.name
		)
		self.assertEqual(doc.budget, project.budget)  # the budget comes from the project
		self.assertFalse(any(r.journal_entry for r in doc.schedule))  # nothing is due yet
		make_payment_entries(doc.name, "2029-03-01")
		doc.reload()
		posted = [r for r in doc.schedule if r.journal_entry]
		self.assertEqual(len(posted), 3)
		self.assertEqual((doc.status, doc.paid_amount), ("Active", 300))
		self.assertEqual(get_project_spent(project.name), 300)

		je = frappe.get_doc("Journal Entry", posted[0].journal_entry)
		self.assertEqual(je.voucher_type, "Recurring Payment")
		rows = frappe.get_all("GL Entry", {"voucher_no": je.name}, ["account", "debit", "credit", "project"])
		self.assertEqual({r.account for r in rows}, {account("Office Rent"), account("Cash")})
		self.assertTrue(all(r.project == project.name for r in rows))

	def test_scheduler_posts_rest_and_completes(self):
		doc = make_recurring_payment(total=600, from_date="2025-01-01", to_date="2025-06-30", submit=False)
		doc.submit()
		doc.reload()
		self.assertEqual((doc.status, doc.paid_amount), ("Completed", 600))
		self.assertEqual(frappe.db.count("Journal Entry", {"recurring_payment": doc.name, "docstatus": 1}), 6)
		post_recurring_payments_daily()  # nothing left: no duplicates
		self.assertEqual(frappe.db.count("Journal Entry", {"recurring_payment": doc.name, "docstatus": 1}), 6)

	def test_future_rows_wait_for_their_date(self):
		start = getdate("2029-01-11")
		doc = make_recurring_payment(total=1200, from_date=start, to_date=add_months(start, 11))
		self.assertFalse(any(r.journal_entry for r in doc.schedule))
		self.assertEqual(len(make_payment_entries(doc.name, add_months(start, 1))), 2)
		doc.reload()
		self.assertEqual(doc.paid_amount, 200)

	def test_stopped_payment_is_skipped(self):
		start = getdate("2029-01-02")
		doc = make_recurring_payment(total=1200, from_date=start, to_date=add_months(start, 11))
		stop(doc.name)
		with self.assertRaises(RecurringPaymentError):
			make_payment_entries(doc.name, add_months(start, 2))
		resume(doc.name)
		self.assertEqual(len(make_payment_entries(doc.name, add_months(start, 2))), 3)

	def test_cancelling_entry_frees_row(self):
		doc = make_recurring_payment(total=300, from_date="2025-01-01", to_date="2025-03-31")
		entries = frappe.get_all(
			"Journal Entry",
			{"recurring_payment": doc.name, "docstatus": 1},
			pluck="name",
			order_by="posting_date",
		)
		frappe.get_doc("Journal Entry", entries[0]).cancel()
		doc.reload()
		self.assertEqual((doc.status, doc.paid_amount), ("Active", 200))
		self.assertFalse(doc.schedule[0].journal_entry)

		self.assertEqual(len(make_payment_entries(doc.name)), 1)
		doc.reload()
		self.assertEqual(doc.status, "Completed")
		for name in frappe.get_all(
			"Journal Entry", {"recurring_payment": doc.name, "docstatus": 1}, pluck="name"
		):
			frappe.get_doc("Journal Entry", name).cancel()
		doc.reload()
		doc.cancel()
		self.assertEqual(doc.status, "Cancelled")

	def test_project_stop_budget_blocks_posting(self):
		project = make_project(budget=250, action="Stop")
		with self.assertRaisesRegex(frappe.ValidationError, "does not fit"):
			make_recurring_payment(
				total=300, from_date="2025-01-01", to_date="2025-03-31", project=project.name, submit=False
			)
		# it fits the share, but a bill took part of the project's budget meanwhile
		make_purchase_invoice(items=[("Office Rent", 100, project.name)])
		with self.assertRaises(BudgetExceededError):
			make_recurring_payment(
				total=240, from_date="2025-01-01", to_date="2025-03-31", project=project.name
			)

	def test_manual_entry_cannot_claim_recurring_type(self):
		je = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"voucher_type": "Recurring Payment",
				"company": self.company.name,
				"posting_date": "2025-03-01",
				"accounts": [
					{"account": account("Office Rent"), "debit": 100},
					{"account": account("Cash"), "credit": 100},
				],
			}
		)
		with self.assertRaises(frappe.ValidationError):
			je.insert()

	def test_rejects_wrong_accounts_and_projects(self):
		with self.assertRaises(frappe.ValidationError):
			make_recurring_payment(expense_account=account("Cash"), submit=False)
		with self.assertRaises(frappe.ValidationError):
			make_recurring_payment(paid_from=account("Office Rent"), submit=False)

		other = make_company("_Test Spend Company 2", "_TS2")
		foreign = make_project("_Test Foreign", company=other.name)
		with self.assertRaises(frappe.ValidationError):
			make_recurring_payment(project=foreign.name, submit=False)

		closed = make_project("_Test Closed", status="Completed")
		with self.assertRaises(InactiveProjectError):
			make_recurring_payment(project=closed.name, submit=False)

	def test_cancel_keeps_payments_and_amendment_covers_the_rest(self):
		start = getdate("2029-01-01")
		doc = make_recurring_payment(total=1200, from_date=start, to_date="2029-12-31")
		make_payment_entries(doc.name, add_months(start, 2))
		doc.reload()
		paid = frappe.get_all("Journal Entry", {"recurring_payment": doc.name, "docstatus": 1}, pluck="name")
		self.assertEqual(len(paid), 3)

		doc.cancel()
		self.assertEqual(doc.status, "Cancelled")
		self.assertEqual(
			frappe.db.count("Journal Entry", {"name": ("in", paid), "docstatus": 1}), 3
		)  # payments made stay on the books

		result = get_amendment("Recurring Payment", doc.name)
		self.assertEqual(result["previous"]["payments"], 3)
		self.assertEqual(result["previous"]["paid_amount"], 300)
		amended = frappe.get_doc(result["doc"])
		self.assertEqual(getdate(amended.from_date), getdate(add_months(start, 3)))
		self.assertEqual(amended.total_amount, 900)

		amended.amendment_reason = "Rent went up"
		amended.from_date = add_months(start, 2)  # already paid
		self.assertRaises(RecurringPaymentError, amended.insert)

		amended.from_date = add_months(start, 3)
		amended.total_amount = 1800
		amended.insert()
		amended.submit()
		self.assertEqual(amended.name, f"{doc.name}-1")
		self.assertEqual(len(amended.schedule), 9)
		self.assertFalse(any(r.journal_entry for r in amended.schedule))  # next payment is next month
		self.assertEqual(len(make_payment_entries(amended.name, add_months(start, 3))), 1)
		self.assertEqual(frappe.db.get_value("Recurring Payment", amended.name, "paid_amount"), 200)


class IntegrationTestRecurringBudget(SpendTestCase):
	def make_budget(self):
		from spend.budgeting.doctype.budget.test_budget import make_budget

		self.cost_center = make_cost_center("_Test Rent CC")
		self.budget = make_budget(
			{account("Office Rent"): 1200, account("Utilities"): 600}, cost_center=self.cost_center
		)

	def rent(self, total, **kw):
		values = {"budget": self.budget.name, "cost_center": self.cost_center, "submit": False}
		return make_recurring_payment(total=total, **{**values, **kw})

	def test_takes_only_what_the_budget_has_free(self):
		self.make_budget()
		first = self.rent(1000, title="_Test First Rent")
		first.submit()
		with self.assertRaisesRegex(frappe.ValidationError, "_Test First Rent"):
			self.rent(300)
		self.rent(200)  # what is left

		# cancelled, it keeps only what it paid
		for name in frappe.get_all(
			"Journal Entry", {"recurring_payment": first.name, "docstatus": 1}, pluck="name"
		):
			frappe.get_doc("Journal Entry", name).cancel()
		make_payment_entries(first.name, "2025-02-28")
		first.reload()
		first.cancel()
		self.assertEqual(first.paid_amount, 166.66)
		self.rent(1033.34)

	def test_account_cost_center_and_dates_come_from_the_budget(self):
		self.make_budget()
		with self.assertRaisesRegex(frappe.ValidationError, "not on Budget"):
			self.rent(100, expense_account=account("Travel Expenses"))
		with self.assertRaisesRegex(frappe.ValidationError, "Pick a cost center"):
			self.rent(100, cost_center=account("Main"))
		with self.assertRaisesRegex(RecurringPaymentError, "Keep the payment dates"):
			self.rent(100, to_date="2026-03-31")
		self.assertEqual(self.rent(100, cost_center=None).cost_center, self.cost_center)

	def test_project_payment_takes_from_the_project_share(self):
		self.make_budget()
		project = make_project(
			"_Test Share Project",
			budget=500,
			accounts=[("Office Rent", 500)],
			budget_doc=self.budget.name,
			cost_center=self.cost_center,
		)
		with self.assertRaisesRegex(frappe.ValidationError, "the share of Project"):
			self.rent(600, project=project.name, budget=None)
		payment = self.rent(400, project=project.name, budget=None)
		payment.submit()
		self.assertEqual(payment.budget, self.budget.name)
		with self.assertRaisesRegex(frappe.ValidationError, "has no budget on Project"):
			self.rent(50, project=project.name, budget=None, expense_account=account("Utilities"))

		# the share can't go below what its recurring payments hold
		project.reload()
		project.budget_accounts[0].budget_amount = 300
		project.budget_amount = 300
		with self.assertRaisesRegex(frappe.ValidationError, payment.name):
			project.save()

		# the project holds its share, so the budget has 700 left for payments without a project
		with self.assertRaises(frappe.ValidationError):
			self.rent(800)
		self.rent(700)

	def test_project_without_share_takes_from_the_budget(self):
		self.make_budget()
		project = make_project("_Test No Share", budget_doc=self.budget.name, cost_center=self.cost_center)
		with self.assertRaisesRegex(frappe.ValidationError, f"Budget {self.budget.name}"):
			self.rent(1300, project=project.name, budget=None)
		payment = self.rent(1000, project=project.name, budget=None)
		payment.submit()

		room = get_recurring_room(project=project.name)
		self.assertFalse(room["share"])
		self.assertEqual(room["free"], 800)
		allocation = get_budget_allocation(self.budget.name)
		self.assertEqual(allocation["held"], 1000)
		self.assertTrue(allocation["recurring"][0]["counted"])
		with self.assertRaisesRegex(frappe.ValidationError, payment.name):
			self.rent(300)  # 200 of Office Rent is free

		# given a share, the share must hold its payments and the budget counts them once
		project.reload()
		project.budget_amount = 500
		with self.assertRaisesRegex(frappe.ValidationError, "take more than its share"):
			project.save()
		project.reload()
		project.budget_amount = 1100
		project.save()
		allocation = get_budget_allocation(self.budget.name)
		self.assertEqual(allocation["held"], 1100)
		self.assertFalse(allocation["recurring"][0]["counted"])
		self.assertTrue(get_recurring_room(project=project.name)["share"])
