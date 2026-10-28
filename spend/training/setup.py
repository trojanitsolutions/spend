"""Install the trainer role and the starter tracks and scenarios.

Missing records are inserted. A starter scenario nobody has edited is refreshed
when the app ships a new version of it; one a trainer has edited is left alone,
so edits survive `bench migrate`. To retire a starter scenario, untick Active
instead of deleting it, or it comes back on the next migrate.
"""

import hashlib
import json
from pathlib import Path

import frappe

from spend.training.access import TRAINER_ROLE

STARTER_PATH = Path(__file__).parent / "starter_content.json"


def after_install():
	create_trainer_role()
	install_starter_content()


def after_migrate():
	create_trainer_role()
	install_starter_content()


def create_trainer_role():
	if not frappe.db.exists("Role", TRAINER_ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": TRAINER_ROLE, "desk_access": 1}).insert(
			ignore_permissions=True
		)


def install_starter_content():
	content = json.loads(STARTER_PATH.read_text())
	for track in content["tracks"]:
		insert_track(track)
	for scenario in content["scenarios"]:
		insert_scenario(scenario)
	frappe.db.commit()


def insert_track(track: dict):
	if frappe.db.exists("Training Track", track["title"]):
		return
	roles = [{"role": role} for role in track["roles"] if frappe.db.exists("Role", role)]
	frappe.get_doc(
		{
			"doctype": "Training Track",
			"title": track["title"],
			"sequence": track.get("sequence", 0),
			"description": track.get("description"),
			"is_active": 1,
			"roles": roles,
		}
	).insert(ignore_permissions=True)


def insert_scenario(scenario: dict):
	version = hashlib.sha1(json.dumps(scenario, sort_keys=True).encode()).hexdigest()
	if not frappe.db.exists("Training Scenario", scenario["title"]):
		doc = frappe.get_doc({"doctype": "Training Scenario", **scenario_fields(scenario)})
		doc.insert(ignore_permissions=True)
		mark_synced(doc, version)
		return

	doc = frappe.get_doc("Training Scenario", scenario["title"])
	if doc.starter_hash == version or edited_since_sync(doc):
		return
	doc.update(scenario_fields(scenario))
	doc.save(ignore_permissions=True)
	mark_synced(doc, version)


def edited_since_sync(doc) -> bool:
	"""True when someone saved the scenario after the installer last wrote it."""
	synced = doc.starter_synced_on or doc.creation
	return frappe.utils.get_datetime(doc.modified) > frappe.utils.get_datetime(synced)


def mark_synced(doc, version: str):
	frappe.db.set_value(
		"Training Scenario",
		doc.name,
		{"starter_hash": version, "starter_synced_on": doc.modified},
		update_modified=False,
	)


def scenario_fields(scenario: dict) -> dict:
	seed = scenario.get("seed_data")
	return {
		"title": scenario["title"],
		"track": scenario["track"],
		"sequence": scenario.get("sequence", 0),
		"difficulty": scenario.get("difficulty", "Beginner"),
		"description": scenario.get("description"),
		"passing_score": scenario.get("passing_score", 70),
		"start_route": scenario.get("start_route"),
		"video_url": scenario.get("video_url"),
		"is_active": 1,
		"allow_guided": 1,
		"allow_practice": 1,
		"seed_data": json.dumps(seed, indent=1) if seed else None,
		"steps": scenario["steps"],
		"quiz": scenario.get("quiz", []),
	}
