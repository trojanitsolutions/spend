"""Who may author training, and who sees which track."""

import frappe
from frappe import _

TRAINER_ROLE = "Spend Trainer"
TRAINER_ROLES = {"System Manager", TRAINER_ROLE}


def is_trainer(user: str | None = None) -> bool:
	user = user or frappe.session.user
	return user == "Administrator" or bool(TRAINER_ROLES & set(frappe.get_roles(user)))


def allowed_tracks(user: str | None = None) -> list[str]:
	"""Names of the active tracks the user may open, in display order."""
	user = user or frappe.session.user
	tracks = frappe.get_all(
		"Training Track",
		filters={"is_active": 1},
		pluck="name",
		order_by="sequence asc, title asc",
	)
	if is_trainer(user):
		return tracks
	roles = set(frappe.get_roles(user))
	track_roles = frappe.get_all(
		"Training Track Role",
		filters={"parenttype": "Training Track", "parent": ["in", tracks or [""]]},
		fields=["parent", "role"],
	)
	permitted = {row.parent for row in track_roles if row.role in roles}
	return [track for track in tracks if track in permitted]


def require_login():
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in to use Training"), frappe.PermissionError)


def require_trainer():
	require_login()
	if not is_trainer():
		frappe.throw(_("Only trainers can do this"), frappe.PermissionError)


def require_scenario_access(scenario: str) -> frappe._dict:
	"""Return the scenario's track and passing score, or raise if the user can't open it.

	Trainers can open inactive scenarios too, to try them while writing them."""
	require_login()
	row = frappe.db.get_value(
		"Training Scenario",
		scenario,
		["name", "track", "is_active", "passing_score"],
		as_dict=True,
	)
	if not row or row.track not in allowed_tracks() or not (row.is_active or is_trainer()):
		frappe.throw(_("You don't have access to this training scenario"), frappe.PermissionError)
	return row
