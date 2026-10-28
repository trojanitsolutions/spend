# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document

from spend.training.sandbox import SEEDABLE_DOCTYPES


class TrainingScenario(Document):
	def validate(self):
		if not (self.allow_guided or self.allow_practice):
			frappe.throw(_("Allow at least one mode: Guided or Practice"))
		self.validate_steps()
		self.validate_quiz()
		self.validate_seed_data()

	def validate_steps(self):
		for step in self.steps:
			step.route = normalize_route(step.route)
			if step.action_type != "Observe" and not step.target:
				frappe.throw(_("Step {0}: a {1} step needs a target").format(step.idx, step.action_type))
		self.start_route = normalize_route(self.start_route)

	def validate_quiz(self):
		for question in self.quiz:
			options = option_lines(question.options)
			if len(options) < 2:
				frappe.throw(_("Question {0}: give at least two answers, one per line").format(question.idx))
			if (question.correct_option or "").strip() not in options:
				frappe.throw(
					_("Question {0}: the correct answer {1} is not one of the options").format(
						question.idx, frappe.bold(question.correct_option)
					)
				)

	def validate_seed_data(self):
		if not (self.seed_data or "").strip():
			return
		try:
			seed = json.loads(self.seed_data)
		except ValueError as e:
			frappe.throw(_("Sample Data is not valid JSON: {0}").format(e))
		if not isinstance(seed, dict):
			frappe.throw(_("Sample Data must be a JSON object of doctype: list of records"))
		for doctype, records in seed.items():
			if doctype not in SEEDABLE_DOCTYPES:
				frappe.throw(
					_("Sample Data cannot create {0}. Allowed: {1}").format(
						frappe.bold(doctype), ", ".join(SEEDABLE_DOCTYPES)
					)
				)
			if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
				frappe.throw(_("Sample Data for {0} must be a list of records").format(doctype))


def normalize_route(route: str | None) -> str:
	"""`bills/new/` → `/bills/new`, and a full `/spend/...` URL loses the app prefix."""
	route = (route or "").strip()
	if not route:
		return ""
	route = "/" + route.strip("/")
	if route == "/spend" or route.startswith("/spend/"):
		route = route[len("/spend") :] or "/"
	return route


def option_lines(options: str | None) -> list[str]:
	return [line.strip() for line in (options or "").splitlines() if line.strip()]
