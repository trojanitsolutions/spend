# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, today
from frappe.utils.nestedset import NestedSet

DONE = ("Completed", "Cancelled")


class CircularReferenceError(frappe.ValidationError):
	pass


class Task(NestedSet):
	nsm_parent_field = "parent_task"

	def validate(self):
		self.subject = (self.subject or "").strip()
		self.validate_project()
		self.validate_dates()
		self.validate_parent()
		self.validate_progress()
		self.validate_status()
		self.validate_depends_on()

	def validate_project(self):
		status = frappe.db.get_value("Project", self.project, "status")
		reopened = self.status not in DONE and (self.is_new() or self.get_db_value("status") in DONE)
		if status != "Open" and reopened:
			frappe.throw(
				_("Project {0} is {1}. Reopen it to add or reopen tasks.").format(
					frappe.bold(self.project), _(status)
				)
			)

	def validate_dates(self):
		if (
			self.exp_start_date
			and self.exp_end_date
			and getdate(self.exp_end_date) < getdate(self.exp_start_date)
		):
			frappe.throw(_("Expected End Date cannot be before the Expected Start Date"))
		start, end = frappe.db.get_value("Project", self.project, ["start_date", "end_date"])
		for fieldname in ("exp_start_date", "exp_end_date"):
			value = self.get(fieldname)
			if not value:
				continue
			if (start and getdate(value) < getdate(start)) or (end and getdate(value) > getdate(end)):
				frappe.throw(
					_("{0} must be within the dates of Project {1}").format(
						_(self.meta.get_label(fieldname)), frappe.bold(self.project)
					)
				)

	def validate_parent(self):
		if not self.parent_task:
			return
		if self.parent_task == self.name:
			frappe.throw(_("A task cannot be its own parent"))
		parent = frappe.db.get_value("Task", self.parent_task, ["is_group", "project"], as_dict=True)
		if not parent or not parent.is_group:
			frappe.throw(_("Parent Task {0} is not a group task").format(frappe.bold(self.parent_task)))
		if parent.project != self.project:
			frappe.throw(
				_("Parent Task {0} belongs to another project").format(frappe.bold(self.parent_task))
			)

	def validate_progress(self):
		if not 0 <= flt(self.progress) <= 100:
			frappe.throw(_("% Progress must be between 0 and 100"))
		if self.status == "Completed":
			self.progress = 100
			self.completed_on = self.completed_on or today()
			self.completed_by = self.completed_by or frappe.session.user
			if getdate(self.completed_on) > getdate(today()):
				frappe.throw(_("Completed On cannot be after today"))
			self.validate_completed_on()
		else:
			self.completed_on = self.completed_by = None

	def validate_completed_on(self):
		project_start = frappe.db.get_value("Project", self.project, "start_date")
		for label, start in (
			(_("the Expected Start Date"), self.exp_start_date),
			(_("the project start"), project_start),
		):
			if start and getdate(self.completed_on) < getdate(start):
				frappe.throw(
					_("Completed On cannot be before {0} ({1})").format(label, frappe.format(start, "Date"))
				)

	def validate_status(self):
		if self.status != "Completed" or self.get_db_value("status") == "Completed":
			return
		for row in self.depends_on:
			status = frappe.db.get_value("Task", row.task, "status")
			if status not in DONE:
				frappe.throw(
					_("Complete or cancel task {0} first: this task depends on it").format(
						frappe.bold(row.subject or row.task)
					)
				)
		if self.is_group and not self.is_new():
			open_children = frappe.get_all(
				"Task",
				filters={"parent_task": self.name, "status": ("not in", DONE)},
				pluck="subject",
				limit=5,
			)
			if open_children:
				frappe.throw(
					_("Complete or cancel its tasks first: {0}").format(", ".join(open_children)),
					title=_("Open Sub Tasks"),
				)

	def validate_depends_on(self):
		seen = set()
		for row in self.depends_on:
			if row.task == self.name:
				frappe.throw(_("Row {0}: a task cannot depend on itself").format(row.idx))
			if row.task in seen:
				frappe.throw(_("Row {0}: task {1} is repeated").format(row.idx, frappe.bold(row.task)))
			seen.add(row.task)
			if frappe.db.get_value("Task", row.task, "project") != self.project:
				frappe.throw(
					_("Row {0}: task {1} belongs to another project").format(row.idx, frappe.bold(row.task))
				)
		self.check_recursion()

	def check_recursion(self):
		"""A task cannot depend, directly or through other tasks, on itself."""
		if self.is_new():
			return
		pending, visited = [r.task for r in self.depends_on], set()
		while pending:
			task = pending.pop()
			if task == self.name:
				frappe.throw(_("Circular dependency: this task depends on itself"), CircularReferenceError)
			if task in visited:
				continue
			visited.add(task)
			pending.extend(
				frappe.get_all(
					"Task Depends On", filters={"parent": task, "parenttype": "Task"}, pluck="task"
				)
			)

	def on_update(self):
		super().on_update()
		update_project_progress(self.project)
		before = self.get_doc_before_save()
		if before and before.project != self.project:
			update_project_progress(before.project)

	def on_trash(self):
		if frappe.db.exists("Task", {"parent_task": self.name}):
			frappe.throw(_("Delete the sub tasks of {0} first").format(frappe.bold(self.subject)))
		dependent = frappe.get_all(
			"Task Depends On", filters={"task": self.name, "parenttype": "Task"}, pluck="parent", limit=1
		)
		if dependent:
			frappe.throw(
				_("Cannot delete task {0}: task {1} depends on it").format(
					frappe.bold(self.subject), frappe.bold(dependent[0])
				)
			)
		super().on_trash()

	def after_delete(self):
		update_project_progress(self.project)

	def update_status(self):
		if self.status not in (*DONE, "Pending Review") and self.exp_end_date:
			if getdate(self.exp_end_date) < getdate(today()):
				self.db_set("status", "Overdue", update_modified=False)


def update_project_progress(project: str):
	"""The share of the project's tasks that are completed or cancelled."""
	statuses = frappe.get_all("Task", filters={"project": project}, pluck="status")
	done = sum(1 for s in statuses if s in DONE)
	percent = flt(done / len(statuses) * 100, 2) if statuses else 0
	frappe.db.set_value("Project", project, "percent_complete", percent, update_modified=False)


def get_open_tasks(project: str, limit: int | None = None) -> list:
	return frappe.get_all(
		"Task",
		filters={"project": project, "status": ("not in", DONE)},
		fields=["name", "subject", "status"],
		order_by="lft",
		limit=limit,
	)


@frappe.whitelist()
def set_multiple_status(names: list | str, status: str, completed_on: str | None = None):
	names = frappe.parse_json(names)
	for name in names:
		task = frappe.get_doc("Task", name)
		task.check_permission("write")
		task.status = status
		if status == "Completed" and completed_on:
			task.completed_on = completed_on
		task.save()


def set_tasks_as_overdue():
	"""Daily: open tasks past their expected end date become Overdue."""
	for name in frappe.get_all(
		"Task",
		filters={"status": ("not in", (*DONE, "Overdue", "Pending Review")), "exp_end_date": ("<", today())},
		pluck="name",
	):
		frappe.get_doc("Task", name).update_status()


@frappe.whitelist()
def get_children(
	doctype: str, parent: str | None = None, project: str | None = None, is_root: bool = False, **kwargs
):
	"""Tasks under a node of the Desk tree view."""
	filters = {"project": project} if project else {}
	filters["parent_task"] = parent if parent and not is_root and parent != "All Tasks" else ("is", "not set")
	return frappe.get_list(
		"Task",
		fields=["name as value", "subject as title", "is_group as expandable"],
		filters=filters,
		order_by="lft",
	)


@frappe.whitelist()
def add_node():
	from frappe.desk.treeview import make_tree_args

	args = frappe.form_dict
	args.update({"name_field": "subject"})
	args = make_tree_args(**args)
	if args.parent_task in ("All Tasks", args.project):
		args.parent_task = None
	frappe.get_doc(args).insert()


def on_doctype_update():
	frappe.db.add_index("Task", ["lft", "rgt"])
