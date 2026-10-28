# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

"""Endpoints for Training in the Spend web app.

Training runs on the real Spend pages. What a trainee creates goes into the
training company (see `sandbox.py`); this module only reads and writes the
training content and the Training Progress rows.
"""

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from spend.training.access import (
	allowed_tracks,
	is_trainer,
	require_login,
	require_scenario_access,
	require_trainer,
)
from spend.training.doctype.training_scenario.training_scenario import option_lines
from spend.training.sandbox import (
	apply_seed_data,
	ensure_training_budget,
	ensure_training_company,
	get_training_company,
	parse_seed,
	reset_company,
)

STEP_FIELDS = (
	"title",
	"route",
	"target",
	"target_kind",
	"target_label",
	"action_type",
	"body",
	"hint",
	"expected_value",
)
SCENARIO_FIELDS = (
	"title",
	"track",
	"difficulty",
	"is_active",
	"passing_score",
	"allow_guided",
	"allow_practice",
	"start_route",
	"video_url",
	"description",
	"seed_data",
)
# the final score when a scenario has a quiz: steps weigh 70%, the quiz 30%
STEP_WEIGHT = 0.7


@frappe.whitelist()
def get_home() -> dict:
	"""Whether the user is a trainer, and the tracks and scenarios they can open."""
	require_login()
	return {
		"is_trainer": is_trainer(),
		"training_company": get_training_company(),
		"tracks": tracks_with_scenarios(allowed_tracks()),
	}


@frappe.whitelist()
def get_scenario(name: str) -> dict:
	require_scenario_access(name)
	doc = frappe.get_doc("Training Scenario", name)
	return {
		"name": doc.name,
		**{field: doc.get(field) for field in SCENARIO_FIELDS},
		"modes": get_modes(doc),
		"steps": [{field: step.get(field) or "" for field in STEP_FIELDS} for step in doc.steps],
		# the answer stays on the server; check_quiz grades it
		"quiz": [
			{"question": q.question, "options": option_lines(q.options)} for q in doc.quiz
		],
		"next_scenario": get_next_scenario(doc),
	}


@frappe.whitelist(methods=["POST"])
def start_training(scenario: str) -> dict:
	"""Make sure the training company and the scenario's sample data exist; return the company."""
	require_scenario_access(scenario)
	company = ensure_training_company()
	ensure_training_budget(company)
	apply_seed_data(parse_seed(frappe.db.get_value("Training Scenario", scenario, "seed_data")), company)
	return {"company": company}


@frappe.whitelist(methods=["POST"])
def check_quiz(scenario: str, answers: list | str) -> dict:
	"""Grade the answers (one per question, in order) and return the score and explanations."""
	require_scenario_access(scenario)
	answers = frappe.parse_json(answers) or []
	quiz = frappe.get_doc("Training Scenario", scenario).quiz
	results = []
	for i, question in enumerate(quiz):
		given = answers[i] if i < len(answers) else None
		results.append(
			{
				"correct": (given or "").strip() == question.correct_option.strip(),
				"correct_option": question.correct_option,
				"explanation": question.explanation or "",
			}
		)
	right = sum(r["correct"] for r in results)
	return {"score": round(right * 100 / len(quiz)) if quiz else 100, "results": results}


@frappe.whitelist(methods=["POST"])
def save_progress(
	scenario: str,
	mode: str,
	step_score: int = 0,
	quiz_score: int | None = None,
	hints_used: int = 0,
	mistakes: int = 0,
	time_taken: int = 0,
) -> dict:
	row = require_scenario_access(scenario)
	if mode not in ("Guided", "Practice"):
		frappe.throw(_("Unknown training mode: {0}").format(mode))

	step_score = clamp_score(step_score)
	has_quiz = quiz_score is not None and frappe.db.exists(
		"Training Quiz Question", {"parenttype": "Training Scenario", "parent": scenario}
	)
	score = (
		round(step_score * STEP_WEIGHT + clamp_score(quiz_score) * (1 - STEP_WEIGHT)) if has_quiz else step_score
	)
	status = "Passed" if score >= cint(row.passing_score) else "Needs Practice"
	progress = frappe.get_doc(
		{
			"doctype": "Training Progress",
			"user": frappe.session.user,
			"scenario": scenario,
			"mode": mode,
			"status": status,
			"score": score,
			"quiz_score": clamp_score(quiz_score) if has_quiz else 0,
			"hints_used": max(0, cint(hints_used)),
			"mistakes": max(0, cint(mistakes)),
			"time_taken": max(0, cint(time_taken)),
			"completed_on": now_datetime(),
		}
	)
	# trainees have no permission on the doctype; this endpoint is the only writer
	progress.insert(ignore_permissions=True)
	return {"name": progress.name, "status": status, "score": score}


@frappe.whitelist()
def get_team_progress() -> dict:
	"""Best result per user and scenario, for trainers."""
	require_trainer()
	attempts = frappe.get_all(
		"Training Progress",
		fields=["user", "full_name", "scenario", "track", "status", "score", "completed_on"],
		order_by="completed_on desc",
		limit=5000,
	)
	summary: dict[tuple, dict] = {}
	for attempt in attempts:
		entry = summary.setdefault(
			(attempt.user, attempt.scenario),
			{
				"user": attempt.user,
				"full_name": attempt.full_name or attempt.user,
				"scenario": attempt.scenario,
				"track": attempt.track,
				"attempts": 0,
				"best_score": 0,
				"passed": False,
				"last_on": attempt.completed_on,
			},
		)
		entry["attempts"] += 1
		entry["best_score"] = max(entry["best_score"], cint(attempt.score))
		entry["passed"] = entry["passed"] or attempt.status == "Passed"
	return {"rows": list(summary.values())}


# ---------------------------------------------------------------- authoring


@frappe.whitelist()
def get_scenario_for_edit(name: str) -> dict:
	"""The full scenario, quiz answers included, for the editor."""
	require_trainer()
	doc = frappe.get_doc("Training Scenario", name)
	return {
		"name": doc.name,
		**{field: doc.get(field) for field in SCENARIO_FIELDS},
		"steps": [{field: step.get(field) or "" for field in STEP_FIELDS} for step in doc.steps],
		"quiz": [
			{
				"question": q.question,
				"options": q.options,
				"correct_option": q.correct_option,
				"explanation": q.explanation or "",
			}
			for q in doc.quiz
		],
		"tracks": frappe.get_all("Training Track", pluck="name", order_by="sequence asc, title asc"),
	}


@frappe.whitelist(methods=["POST"])
def create_scenario(track: str, title: str, start_route: str | None = None) -> dict:
	require_trainer()
	doc = frappe.get_doc(
		{
			"doctype": "Training Scenario",
			"track": track,
			"title": (title or "").strip(),
			"start_route": start_route,
			"is_active": 0,
		}
	).insert(ignore_permissions=True)
	return {"name": doc.name}


@frappe.whitelist(methods=["POST"])
def save_scenario(name: str, values: dict | str) -> dict:
	"""Save the editor: scenario fields, and the steps and quiz when given (each replaces the table)."""
	require_trainer()
	values = frappe.parse_json(values) or {}
	doc = frappe.get_doc("Training Scenario", name)
	doc.update({field: values[field] for field in SCENARIO_FIELDS if field in values and field != "title"})
	if "steps" in values:
		doc.set("steps", [pick(step, STEP_FIELDS) for step in values["steps"]])
	if "quiz" in values:
		doc.set(
			"quiz",
			[pick(q, ("question", "options", "correct_option", "explanation")) for q in values["quiz"]],
		)
	doc.save(ignore_permissions=True)
	return get_scenario_for_edit(doc.name)


@frappe.whitelist(methods=["POST"])
def save_steps(scenario: str, steps: list | str) -> dict:
	"""The recorder: replace the scenario's steps."""
	return save_scenario(scenario, {"steps": frappe.parse_json(steps) or []})


@frappe.whitelist(methods=["POST"])
def reset_training_data() -> dict:
	require_trainer()
	company = get_training_company()
	if not company:
		return {"deleted": 0, "failed": []}
	return reset_company(company)


# ---------------------------------------------------------------- helpers


def tracks_with_scenarios(tracks: list[str]) -> list[dict]:
	if not tracks:
		return []
	track_docs = frappe.get_all(
		"Training Track",
		filters={"name": ["in", tracks]},
		fields=["name", "title", "description"],
	)
	filters = {"track": ["in", tracks]}
	if not is_trainer():
		filters["is_active"] = 1
	scenarios = frappe.get_all(
		"Training Scenario",
		filters=filters,
		fields=[
			"name",
			"title",
			"track",
			"description",
			"difficulty",
			"is_active",
			"passing_score",
			"allow_guided",
			"allow_practice",
			"video_url",
		],
		order_by="sequence asc, title asc",
	)
	best = get_best_results(frappe.session.user)
	by_track: dict[str, list] = {}
	for scenario in scenarios:
		scenario["modes"] = get_modes(scenario)
		scenario["best"] = best.get(scenario.name)
		by_track.setdefault(scenario.track, []).append(scenario)

	order = {name: i for i, name in enumerate(tracks)}
	track_docs.sort(key=lambda t: order[t.name])
	for track in track_docs:
		track["scenarios"] = by_track.get(track.name, [])
	return track_docs


def get_best_results(user: str) -> dict[str, dict]:
	"""For each scenario: best score, whether it was ever passed, and the last attempt time."""
	attempts = frappe.get_all(
		"Training Progress",
		filters={"user": user},
		fields=["scenario", "status", "score", "completed_on"],
		order_by="completed_on desc",
	)
	best: dict[str, dict] = {}
	for attempt in attempts:
		entry = best.setdefault(attempt.scenario, {"score": 0, "passed": False, "last_on": attempt.completed_on})
		entry["score"] = max(entry["score"], cint(attempt.score))
		entry["passed"] = entry["passed"] or attempt.status == "Passed"
	return best


def get_modes(scenario) -> list[str]:
	modes = [mode for mode in ("Guided", "Practice") if scenario.get(f"allow_{mode.lower()}")]
	return modes or ["Guided"]


def get_next_scenario(doc) -> str | None:
	names = frappe.get_all(
		"Training Scenario",
		filters={"track": doc.track, "is_active": 1},
		pluck="name",
		order_by="sequence asc, title asc",
	)
	if doc.name in names:
		i = names.index(doc.name)
		if i + 1 < len(names):
			return names[i + 1]
	return None


def clamp_score(score) -> int:
	return max(0, min(100, cint(score)))


def pick(row: dict, fields: tuple) -> dict:
	return {field: row.get(field) for field in fields if field in row}
