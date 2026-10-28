# Copyright (c) 2026, Trojan IT Solutions and Contributors
# See license.txt

import json

import frappe

from spend.tests.utils import (
	TEST_COMPANY,
	SpendTestCase,
	ensure_open_budget,
	set_approvals,
	make_item,
	make_purchase_invoice,
	make_supplier,
	make_user,
)
from spend.training import api
from spend.training.access import allowed_tracks
from spend.training.sandbox import ensure_training_company

TRAINEE = "_spend_trainee@example.com"
OUTSIDER = "_spend_training_outsider@example.com"
TRAINER = "_spend_trainer@example.com"
TRACK = "_Test Training Track"
SCENARIO = "_Test Training Scenario"


def make_track():
	if frappe.db.exists("Training Track", TRACK):
		return TRACK
	frappe.get_doc(
		{"doctype": "Training Track", "title": TRACK, "is_active": 1, "roles": [{"role": "Accounts Manager"}]}
	).insert()
	return TRACK


def make_scenario(**kw):
	values = {
		"doctype": "Training Scenario",
		"title": SCENARIO,
		"track": make_track(),
		"is_active": 1,
		"passing_score": 70,
		"allow_guided": 1,
		"allow_practice": 1,
		"steps": [
			{"title": "New bill", "route": "/bills", "target": "bills.new", "action_type": "Click"},
			{
				"title": "Supplier",
				"route": "/bills/new",
				"target": "bill.supplier",
				"action_type": "Select Option",
				"expected_value": "Acme",
			},
		],
		"quiz": [
			{"question": "Drafts post?", "options": "Yes\nNo", "correct_option": "No"},
			{"question": "Bills are for?", "options": "Suppliers\nCustomers", "correct_option": "Suppliers"},
		],
	}
	values.update(kw)
	return frappe.get_doc(values).insert()


class TestTraining(SpendTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_user(TRAINEE, ["Accounts Manager"])
		make_user(OUTSIDER, ["General Manager"])
		make_user(TRAINER, ["Accounts Manager", "Spend Trainer"])

	def setUp(self):
		super().setUp()
		self.addCleanup(frappe.set_user, "Administrator")

	def test_track_visible_only_to_its_roles_and_trainers(self):
		make_track()
		self.assertIn(TRACK, allowed_tracks(TRAINEE))
		self.assertNotIn(TRACK, allowed_tracks(OUTSIDER))
		self.assertIn(TRACK, allowed_tracks(TRAINER))

	def test_outsider_cannot_open_scenario(self):
		make_scenario()
		frappe.set_user(OUTSIDER)
		self.assertRaises(frappe.PermissionError, api.get_scenario, SCENARIO)

	def test_quiz_answers_stay_on_the_server(self):
		make_scenario()
		frappe.set_user(TRAINEE)
		scenario = api.get_scenario(SCENARIO)
		self.assertEqual(scenario["quiz"][0], {"question": "Drafts post?", "options": ["Yes", "No"]})
		result = api.check_quiz(SCENARIO, ["No", "Customers"])
		self.assertEqual(result["score"], 50)
		self.assertEqual([r["correct"] for r in result["results"]], [True, False])

	def test_only_trainers_author_and_reset(self):
		make_scenario()
		frappe.set_user(TRAINEE)
		self.assertRaises(frappe.PermissionError, api.save_steps, SCENARIO, [])
		self.assertRaises(frappe.PermissionError, api.reset_training_data)
		self.assertRaises(frappe.PermissionError, api.create_scenario, TRACK, "_Nope")

		frappe.set_user(TRAINER)
		steps = [{"title": "Look", "route": "bills", "target": "", "action_type": "Observe"}]
		saved = api.save_steps(SCENARIO, steps)
		self.assertEqual(len(saved["steps"]), 1)
		self.assertEqual(saved["steps"][0]["route"], "/bills")

	def test_progress_weighs_steps_and_quiz(self):
		make_scenario()
		frappe.set_user(TRAINEE)
		passed = api.save_progress(SCENARIO, "Practice", step_score=80, quiz_score=50)
		self.assertEqual(passed["score"], 71)  # 80 × 0.7 + 50 × 0.3
		self.assertEqual(passed["status"], "Passed")
		failed = api.save_progress(SCENARIO, "Guided", step_score=60, quiz_score=None)
		self.assertEqual((failed["score"], failed["status"]), (60, "Needs Practice"))
		self.assertRaises(frappe.ValidationError, api.save_progress, SCENARIO, "Watch")

		frappe.set_user(TRAINER)
		rows = [r for r in api.get_team_progress()["rows"] if r["scenario"] == SCENARIO]
		self.assertEqual(len(rows), 1)
		self.assertEqual((rows[0]["attempts"], rows[0]["best_score"], rows[0]["passed"]), (2, 71, True))

	def test_start_creates_training_company_and_sample_data(self):
		seed = {"Supplier": [{"supplier_name": "_Test Training Supplier"}]}
		make_scenario(seed_data=json.dumps(seed))
		frappe.set_user(TRAINEE)
		company = api.start_training(SCENARIO)["company"]
		self.assertTrue(frappe.db.get_value("Company", company, "is_training"))
		self.assertTrue(frappe.db.exists("Account", {"company": company}))
		self.assertTrue(frappe.db.exists("Supplier", "_Test Training Supplier"))
		# expenses need budgeted accounts, so the company gets an open Budget
		self.assertEqual(frappe.db.count("Budget", {"company": company, "docstatus": 1}), 1)
		# a second start reuses both
		self.assertEqual(api.start_training(SCENARIO)["company"], company)

	def test_training_budget_is_posted_while_approvals_are_on(self):
		set_approvals(True)
		make_scenario()
		frappe.set_user(TRAINEE)
		company = api.start_training(SCENARIO)["company"]
		frappe.set_user("Administrator")
		self.assertEqual(
			frappe.db.get_value("Budget", {"company": company}, ["docstatus", "workflow_state"]),
			(1, "Approved"),
		)

	def test_reset_removes_only_training_documents(self):
		company = ensure_training_company()
		ensure_open_budget(2025, company)
		expense = frappe.db.get_value("Company", company, "default_expense_account")
		training_bill = frappe.get_doc(
			{
				"doctype": "Purchase Invoice",
				"supplier": make_supplier().name,
				"company": company,
				"posting_date": "2025-03-01",
				"due_date": "2025-03-31",
				"items": [{"item_code": make_item().name, "expense_account": expense, "qty": 1, "rate": 100}],
			}
		).insert()
		training_bill.submit()
		real_bill = make_purchase_invoice()

		frappe.set_user(TRAINER)
		result = api.reset_training_data()
		self.assertEqual(result["failed"], [])
		self.assertFalse(frappe.db.exists("Purchase Invoice", training_bill.name))
		self.assertFalse(frappe.db.exists("GL Entry", {"company": company}))
		self.assertTrue(frappe.db.exists("Purchase Invoice", real_bill.name))
		self.assertTrue(frappe.db.exists("GL Entry", {"company": TEST_COMPANY}))

	def test_training_flag_stays_while_documents_exist(self):
		company = ensure_training_company()
		frappe.get_doc(
			{"doctype": "Expense Category", "category_name": "_Test Training", "company": company, "is_parent_category": 1}
		).insert()
		doc = frappe.get_doc("Company", company)
		doc.is_training = 0
		self.assertRaises(frappe.ValidationError, doc.save)

	def test_scenario_validation(self):
		bad_quiz = [{"question": "Q", "options": "A\nB", "correct_option": "C"}]
		self.assertRaises(frappe.ValidationError, make_scenario, quiz=bad_quiz)
		bad_seed = json.dumps({"Purchase Invoice": [{}]})
		self.assertRaises(frappe.ValidationError, make_scenario, seed_data=bad_seed)
		no_target = [{"title": "Click", "action_type": "Click", "target": ""}]
		self.assertRaises(frappe.ValidationError, make_scenario, steps=no_target)
