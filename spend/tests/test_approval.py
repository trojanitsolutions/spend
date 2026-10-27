# Copyright (c) 2026, Trojan IT Solutions and Contributors
# See license.txt

import frappe
from frappe.model.workflow import WorkflowTransitionError
from frappe.utils import add_days, nowdate

from spend.spend.accounting import InactiveProjectError
from spend.spend.amendment import get_amendment
from spend.spend.approval import (
	APPROVE,
	APPROVED,
	PENDING_GM,
	PENDING_MANAGER,
	REJECT,
	REJECTED,
	RESUBMIT,
	REVISE,
	SEND,
	ApprovalRequiredError,
	apply_action,
	get_pending_approvals,
)
from spend.spend.notifications import (
	APPROVAL,
	BUDGET_ALERT,
	get_bills_due_subject,
	get_counts,
	get_notifications,
	mark_read,
	notify,
	notify_recurring_failed,
)
from spend.tests.utils import (
	TEST_COMPANY,
	SpendTestCase,
	account,
	make_journal_entry,
	make_project,
	make_purchase_invoice,
	make_recurring_payment,
	make_supplier,
	make_supplier_payment,
	make_user,
	set_approvals,
)

PREPARER = "_spend_preparer@example.com"
MANAGER = "_spend_manager@example.com"
MANAGER_2 = "_spend_manager2@example.com"
GM = "_spend_gm@example.com"


class TestApproval(SpendTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_user(PREPARER, ["Accounts User"])
		make_user(MANAGER, ["Accounts Manager"])
		make_user(MANAGER_2, ["Accounts Manager"])
		make_user(GM, ["General Manager"])
		make_supplier()

	def setUp(self):
		super().setUp()
		set_approvals(True)
		self.addCleanup(frappe.set_user, "Administrator")

	def as_user(self, user, fn, *args, **kw):
		frappe.set_user(user)
		try:
			return fn(*args, **kw)
		finally:
			frappe.set_user("Administrator")

	def act(self, user, doc, action, reason=None):
		self.as_user(user, apply_action, doc.doctype, doc.name, action, reason)
		return frappe.get_doc(doc.doctype, doc.name)

	def draft_bill(self, **kw):
		return self.as_user(PREPARER, make_purchase_invoice, submit=False, **kw)

	def approve_fully(self, doc, preparer=PREPARER):
		doc = self.act(preparer, doc, SEND)
		doc = self.act(MANAGER, doc, APPROVE)
		return self.act(GM, doc, APPROVE)

	def logs_for(self, user, doc=None, notification_type=APPROVAL):
		filters = {"for_user": user, "type": notification_type}
		if doc:
			filters.update(document_type=doc.doctype, document_name=doc.name)
		return frappe.get_all("Notification Log", filters=filters, pluck="subject")

	# ------------------------------------------------------------ flow

	def test_bill_needs_manager_then_gm(self):
		bill = self.draft_bill()
		self.assertEqual(bill.workflow_state, "Draft")

		bill = self.act(PREPARER, bill, SEND)
		self.assertEqual((bill.workflow_state, bill.docstatus), (PENDING_MANAGER, 0))
		bill = self.act(MANAGER, bill, APPROVE)
		self.assertEqual((bill.workflow_state, bill.docstatus), (PENDING_GM, 0))
		bill = self.act(GM, bill, APPROVE)
		self.assertEqual((bill.workflow_state, bill.docstatus), (APPROVED, 1))
		self.assertTrue(frappe.db.exists("GL Entry", {"voucher_no": bill.name, "is_cancelled": 0}))

	def test_submit_without_approval_is_blocked(self):
		bill = self.draft_bill()
		with self.assertRaises(ApprovalRequiredError):
			bill.submit()

		bill = self.act(PREPARER, bill, SEND)
		bill = self.act(MANAGER, bill, APPROVE)
		with self.assertRaises(ApprovalRequiredError):
			frappe.get_doc(bill.doctype, bill.name).submit()

	def test_only_the_right_role_approves_each_level(self):
		bill = self.act(PREPARER, self.draft_bill(), SEND)
		with self.assertRaises(WorkflowTransitionError):
			self.act(PREPARER, bill, APPROVE)
		with self.assertRaises(WorkflowTransitionError):
			self.act(GM, bill, APPROVE)

		bill = self.act(MANAGER, bill, APPROVE)
		with self.assertRaises(WorkflowTransitionError):
			self.act(MANAGER_2, bill, APPROVE)

	def test_creator_cannot_approve_own_document(self):
		entry = self.as_user(
			MANAGER,
			make_journal_entry,
			account("Office Rent"),
			account("Cash"),
			500,
			"2025-04-01",
			submit=False,
		)
		entry = self.act(MANAGER, entry, SEND)
		with self.assertRaises(frappe.ValidationError):
			self.act(MANAGER, entry, APPROVE)
		entry = self.act(MANAGER_2, entry, APPROVE)
		self.assertEqual(entry.workflow_state, PENDING_GM)

	def test_reject_needs_reason_and_can_be_resubmitted(self):
		bill = self.act(PREPARER, self.draft_bill(), SEND)
		with self.assertRaises(frappe.ValidationError):
			self.act(MANAGER, bill, REJECT)

		bill = self.act(MANAGER, bill, REJECT, reason="Wrong amount")
		self.assertEqual((bill.workflow_state, bill.docstatus), (REJECTED, 0))
		self.assertTrue(
			frappe.db.exists(
				"Comment",
				{
					"reference_name": bill.name,
					"comment_type": "Comment",
					"content": ("like", "%Wrong amount%"),
				},
			)
		)
		rejected = frappe.get_all(
			"Notification Log",
			filters={"for_user": PREPARER, "document_name": bill.name, "subject": ("like", "%rejected%")},
			pluck="email_content",
		)
		self.assertEqual(rejected, ["Reason: Wrong amount"])

		bill = self.act(PREPARER, bill, RESUBMIT)
		self.assertEqual(bill.workflow_state, PENDING_MANAGER)

	def test_pending_list_shows_only_what_user_can_approve(self):
		bill = self.act(PREPARER, self.draft_bill(), SEND)
		names = lambda user: [r["name"] for r in self.as_user(user, get_pending_approvals, TEST_COMPANY)]  # noqa: E731
		self.assertIn(bill.name, names(MANAGER))
		self.assertNotIn(bill.name, names(GM))

		self.assertEqual(self.as_user(MANAGER, get_counts, TEST_COMPANY)["pending"], 1)

		self.act(MANAGER, bill, APPROVE)
		self.assertNotIn(bill.name, names(MANAGER))
		self.assertIn(bill.name, names(GM))
		self.assertEqual(self.as_user(GM, get_counts, TEST_COMPANY)["pending"], 1)

	def test_system_entries_of_approved_documents_post_directly(self):
		rp = self.as_user(
			PREPARER,
			make_recurring_payment,
			total=300,
			from_date="2025-01-01",
			to_date="2025-03-31",
			submit=False,
		)
		rp = self.approve_fully(rp)
		self.assertEqual((rp.docstatus, rp.status), (1, "Completed"))
		posted = [r.journal_entry for r in rp.schedule if r.journal_entry]
		self.assertEqual(len(posted), 3)
		self.assertEqual(frappe.db.get_value("Journal Entry", posted[0], "docstatus"), 1)

	def test_approved_payment_can_be_cancelled(self):
		from spend.api import cancel_doc

		bill = self.approve_fully(self.draft_bill(posting_date="2030-01-01", due_date="2030-12-31"))
		payment = self.as_user(
			PREPARER, make_supplier_payment, [(bill.name, 5000)], submit=False, posting_date="2030-02-01"
		)
		self.assertRaisesRegex(
			frappe.ValidationError,
			"Only a submitted",
			self.as_user,
			PREPARER,
			cancel_doc,
			payment.doctype,
			payment.name,
		)
		payment = self.approve_fully(payment)
		self.assertEqual(frappe.db.get_value("Purchase Invoice", bill.name, "outstanding_amount"), 0)

		self.as_user(PREPARER, cancel_doc, payment.doctype, payment.name)
		self.assertEqual(
			frappe.db.get_value("Supplier Payment", payment.name, ["docstatus", "workflow_state"]),
			(2, "Cancelled"),
		)
		self.assertEqual(
			frappe.db.get_value("Purchase Invoice", bill.name, ["outstanding_amount", "status"]),
			(5000, "Unpaid"),
		)

	def test_amended_budget_needs_approval_and_cancel_notifies(self):
		from spend.spend.doctype.budget.test_budget import make_budget

		frappe.set_user(MANAGER)
		budget = make_budget({account("Office Rent"): 1000}, submit=False)
		frappe.set_user("Administrator")
		budget = self.act(MANAGER, budget, SEND)
		budget = self.act(MANAGER_2, budget, APPROVE)
		budget = self.act(GM, budget, APPROVE)
		self.assertEqual(budget.docstatus, 1)

		self.as_user(MANAGER_2, budget.cancel)
		self.assertEqual(frappe.db.get_value("Budget", budget.name, "workflow_state"), "Cancelled")
		subjects = self.logs_for(GM, budget) + self.logs_for(MANAGER, budget)
		self.assertEqual(sum("was cancelled" in s for s in subjects), 2)

		amended = frappe.get_doc(get_amendment("Budget", budget.name)["doc"])
		amended.update({"amendment_reason": "More rent", "accounts": []})
		amended.append("accounts", {"account": account("Office Rent"), "budget_amount": 1500})
		self.as_user(MANAGER, amended.insert)
		with self.assertRaises(ApprovalRequiredError):
			amended.submit()

		amended = self.act(MANAGER, amended, SEND)
		message = frappe.db.get_value(
			"Notification Log", {"for_user": MANAGER_2, "document_name": amended.name}, "email_content"
		)
		self.assertIn(f"Amends {budget.name} · net change +", message)
		amended = self.act(MANAGER_2, amended, APPROVE)
		self.assertEqual(amended.docstatus, 0)
		amended = self.act(GM, amended, APPROVE)
		self.assertEqual((amended.workflow_state, amended.docstatus), (APPROVED, 1))

	def test_unapproved_project_cannot_be_booked(self):
		project = make_project("_Test Approval Project", budget=10000)
		self.assertEqual(project.workflow_state, "Draft")
		with self.assertRaises(InactiveProjectError):
			make_purchase_invoice(items=[("Office Rent", 100, project.name)], submit=False)

		project = self.approve_fully(project, preparer="Administrator")
		self.assertEqual(project.workflow_state, APPROVED)
		make_purchase_invoice(items=[("Office Rent", 100, project.name)], submit=False)

		project.budget_amount = 20000
		with self.assertRaises(frappe.ValidationError):
			project.save()

		project = self.act(MANAGER, project, REVISE)
		self.assertEqual(project.workflow_state, "Draft")
		with self.assertRaises(InactiveProjectError):
			make_purchase_invoice(items=[("Office Rent", 100, project.name)], submit=False)

	# ------------------------------------------------------------ notifications

	def test_each_step_notifies_the_next_person(self):
		bill = self.act(PREPARER, self.draft_bill(), SEND)
		self.assertEqual(len(self.logs_for(MANAGER, bill)), 1)
		self.assertEqual(len(self.logs_for(MANAGER_2, bill)), 1)
		self.assertFalse(self.logs_for(GM, bill))

		bill = self.act(MANAGER, bill, APPROVE)
		self.assertEqual(len(self.logs_for(GM, bill)), 1)
		self.assertEqual(len(self.logs_for(PREPARER, bill)), 1)

		self.act(GM, bill, APPROVE)
		self.assertTrue(any("approved by" in s and "posted" in s for s in self.logs_for(PREPARER, bill)))

	def test_budget_alert_fires_once_per_crossing(self):
		set_approvals(False)
		project = make_project("_Test Alert Project", budget=1000)
		alerts = lambda: self.logs_for(MANAGER, project, BUDGET_ALERT)  # noqa: E731

		make_purchase_invoice(items=[("Office Rent", 500, project.name)])
		self.assertEqual(alerts(), [])
		make_purchase_invoice(items=[("Office Rent", 350, project.name)])
		self.assertEqual(len(alerts()), 1)
		self.assertIn("85.0%", alerts()[0])
		make_purchase_invoice(items=[("Office Rent", 50, project.name)])
		self.assertEqual(len(alerts()), 1)
		make_purchase_invoice(items=[("Office Rent", 200, project.name)])
		self.assertEqual(len(alerts()), 2)
		self.assertTrue(any("over budget" in s for s in alerts()))

	def test_bills_due_digest(self):
		set_approvals(False)
		today = frappe.utils.getdate(nowdate())
		make_purchase_invoice(posting_date=add_days(today, -40), due_date=add_days(today, -5))
		make_purchase_invoice(posting_date=add_days(today, -1), due_date=add_days(today, 2))
		make_purchase_invoice(posting_date=add_days(today, -1), due_date=add_days(today, 20))

		subject = get_bills_due_subject(TEST_COMPANY, "INR", today, add_days(today, 3))
		self.assertIn("1 due by", subject)
		self.assertIn("1 overdue", subject)
		self.assertIsNone(
			get_bills_due_subject(TEST_COMPANY, "INR", add_days(today, -60), add_days(today, -50))
		)

	def test_failed_recurring_posting_notifies_owner_and_managers(self):
		set_approvals(False)
		rp = self.as_user(PREPARER, make_recurring_payment, from_date="2030-01-01", to_date="2030-12-31")
		notify_recurring_failed(rp.name, "Budget exceeded")
		for user in (PREPARER, MANAGER):
			self.assertEqual(len(self.logs_for(user, rp, "Recurring Payment")), 1)

	def test_users_only_see_and_mark_their_own_notifications(self):
		notify([MANAGER, GM], "Hello", notification_type=APPROVAL)
		frappe.set_user(MANAGER)
		mine = get_notifications(unread_only=1)
		self.assertTrue(mine)
		self.assertTrue(
			all(frappe.db.get_value("Notification Log", n.name, "for_user") == MANAGER for n in mine)
		)
		mark_read()
		self.assertFalse(get_notifications(unread_only=1))
		frappe.set_user("Administrator")
		self.assertTrue(frappe.db.exists("Notification Log", {"for_user": GM, "read": 0}))
