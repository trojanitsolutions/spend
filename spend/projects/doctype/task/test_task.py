# Copyright (c) 2026, Trojan IT Solutions and Contributors
# See license.txt

import frappe
from frappe.utils import add_days, today

from spend.projects.doctype.task.task import CircularReferenceError, set_tasks_as_overdue
from spend.tests.utils import SpendTestCase, make_project

IGNORE_TEST_RECORD_DEPENDENCIES = ["Company", "Account", "Cost Center", "Fiscal Year", "Project"]


def make_task(project, subject, **kw):
	return frappe.get_doc({"doctype": "Task", "project": project, "subject": subject, **kw}).insert()


def set_status(doc, status):
	doc.reload()
	doc.status = status
	doc.save()
	return doc


class IntegrationTestTask(SpendTestCase):
	def setUp(self):
		super().setUp()
		self.project = make_project()

	def test_project_completes_only_when_tasks_are_done(self):
		design = make_task(self.project.name, "Design")
		build = make_task(self.project.name, "Build")
		self.assertRaisesRegex(
			frappe.ValidationError, "before marking it completed", set_status, self.project, "Completed"
		)

		set_status(design, "Completed")
		set_status(build, "Cancelled")
		set_status(self.project, "Completed")
		self.assertEqual(self.project.status, "Completed")

	def test_project_cancels_with_open_tasks(self):
		make_task(self.project.name, "Design")
		self.assertEqual(set_status(self.project, "Cancelled").status, "Cancelled")

	def test_no_new_or_reopened_tasks_on_a_closed_project(self):
		task = make_task(self.project.name, "Design", status="Completed")
		set_status(self.project, "Completed")
		self.assertRaisesRegex(frappe.ValidationError, "Reopen it", make_task, self.project.name, "Late")
		self.assertRaisesRegex(frappe.ValidationError, "Reopen it", set_status, task, "Open")

	def test_dependencies(self):
		design = make_task(self.project.name, "Design")
		build = make_task(self.project.name, "Build", depends_on=[{"task": design.name}])
		self.assertRaisesRegex(frappe.ValidationError, "depends on it", set_status, build, "Completed")
		set_status(design, "Completed")
		self.assertEqual(set_status(build, "Completed").progress, 100)

		design.reload()
		design.append("depends_on", {"task": build.name})
		self.assertRaises(CircularReferenceError, design.save)

		other = make_project(name="_Test Other Project")
		self.assertRaisesRegex(
			frappe.ValidationError,
			"another project",
			make_task,
			other.name,
			"Elsewhere",
			depends_on=[{"task": design.name}],
		)

	def test_group_tasks(self):
		phase = make_task(self.project.name, "Phase 1", is_group=1)
		step = make_task(self.project.name, "Step", parent_task=phase.name)
		self.assertRaisesRegex(
			frappe.ValidationError, "not a group", make_task, self.project.name, "X", parent_task=step.name
		)
		self.assertRaisesRegex(frappe.ValidationError, "its tasks first", set_status, phase, "Completed")
		set_status(step, "Completed")
		set_status(phase, "Completed")
		self.assertRaises(frappe.ValidationError, phase.delete)

	def test_percent_complete(self):
		tasks = [make_task(self.project.name, f"T{i}") for i in range(4)]
		set_status(tasks[0], "Completed")
		self.assertEqual(frappe.db.get_value("Project", self.project.name, "percent_complete"), 25)
		set_status(tasks[1], "Cancelled")
		self.assertEqual(frappe.db.get_value("Project", self.project.name, "percent_complete"), 50)
		tasks[2].delete()
		self.assertAlmostEqual(frappe.db.get_value("Project", self.project.name, "percent_complete"), 66.67)

	def test_overdue(self):
		self.project.db_set({"start_date": None, "end_date": None})
		late = make_task(self.project.name, "Late", exp_end_date=add_days(today(), -1))
		review = make_task(
			self.project.name, "Review", exp_end_date=add_days(today(), -1), status="Pending Review"
		)
		set_tasks_as_overdue()
		self.assertEqual(frappe.db.get_value("Task", late.name, "status"), "Overdue")
		self.assertEqual(frappe.db.get_value("Task", review.name, "status"), "Pending Review")

	def test_project_summary_lists_tasks(self):
		from spend.projects.doctype.project.project import get_project_summary

		make_task(self.project.name, "Design")
		make_task(self.project.name, "Build", status="Completed")
		summary = get_project_summary(self.project.name)
		self.assertEqual(len(summary["tasks"]), 2)
		self.assertEqual(summary["open_tasks"], 1)

	def test_completed_on(self):
		from spend.projects.doctype.task.task import set_multiple_status

		self.project.db_set("start_date", "2025-01-01")
		task = make_task(self.project.name, "Design")
		for completed_on, error in ((add_days(today(), 1), "after today"), ("2024-12-31", "project start")):
			task.reload()
			task.status, task.completed_on = "Completed", completed_on
			self.assertRaisesRegex(frappe.ValidationError, error, task.save)

		set_multiple_status([task.name], "Completed", completed_on="2025-03-04")
		self.assertEqual(str(frappe.db.get_value("Task", task.name, "completed_on")), "2025-03-04")
