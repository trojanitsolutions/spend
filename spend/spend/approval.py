# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

"""One-step approval by the General Manager.

Built on Frappe Workflow, so Desk shows the approval buttons. A plain `submit()`
bypasses the workflow, so `check_approved` guards every submit as well.
"""

import frappe
from frappe import _
from frappe.model.workflow import apply_workflow, get_transitions, has_approval_access
from frappe.utils import flt

DRAFT = "Draft"
PENDING_GM = "Pending GM Approval"
APPROVED = "Approved"
REJECTED = "Rejected"
CANCELLED = "Cancelled"
PENDING_STATES = (PENDING_GM,)

SEND, APPROVE, REJECT, RESUBMIT, REVISE = "Send for Approval", "Approve", "Reject", "Resubmit", "Revise"

# doctype -> Spend Settings check that turns its approval on
APPROVAL_DOCTYPES = {
	"Purchase Invoice": "approve_purchase_invoice",
	"Supplier Payment": "approve_supplier_payment",
	"Journal Entry": "approve_journal_entry",
	"Recurring Payment": "approve_recurring_payment",
	"Budget": "approve_budget",
	"Project": "approve_project",
}

# Journal Entries posted by the system for documents that were approved themselves
AUTO_ENTRY_TYPES = ("Depreciation Entry", "Asset Capitalization", "Recurring Payment")

STATE_STYLES = {
	DRAFT: None,
	PENDING_GM: "Warning",
	APPROVED: "Success",
	REJECTED: "Danger",
	CANCELLED: "Inverse",
}


class ApprovalRequiredError(frappe.ValidationError):
	pass


def workflow_name(doctype: str) -> str:
	return f"{doctype} Approval"


def is_approval_required(doctype: str) -> bool:
	field = APPROVAL_DOCTYPES.get(doctype)
	return bool(
		field
		and frappe.db.get_single_value("Spend Settings", field, cache=False)
		and frappe.get_meta(doctype).get_workflow()
	)


def get_active_approvals() -> list[str]:
	return [doctype for doctype in APPROVAL_DOCTYPES if is_approval_required(doctype)]


def check_approved(doc):
	"""Block a submit that was not approved."""
	if doc.doctype == "Journal Entry" and doc.voucher_type in AUTO_ENTRY_TYPES:
		return
	if is_approval_required(doc.doctype) and doc.get("workflow_state") != APPROVED:
		frappe.throw(
			_(
				"{0} {1} needs approval by the General Manager before it is posted"
			).format(_(doc.doctype), frappe.bold(doc.name)),
			ApprovalRequiredError,
			title=_("Approval Required"),
		)


def set_cancelled_state(doc, method=None):
	"""doc_events on_cancel: Frappe does not move the workflow on cancel, so mark it here."""
	if doc.get("workflow_state") and doc.meta.get_workflow():
		doc.db_set("workflow_state", CANCELLED, update_modified=False)


def is_project_approved(project: str) -> bool:
	if not is_approval_required("Project"):
		return True
	return frappe.db.get_value("Project", project, "workflow_state") == APPROVED


# ---------------------------------------------------------------- setup


def setup_workflows():
	"""Create or update one approval workflow per doctype. Safe to run again."""
	for state, style in STATE_STYLES.items():
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc(
				{"doctype": "Workflow State", "workflow_state_name": state, "style": style}
			).insert(ignore_permissions=True)
	for action in (SEND, APPROVE, REJECT, RESUBMIT, REVISE):
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": action}).insert(
				ignore_permissions=True
			)

	settings = frappe.get_single("Spend Settings")
	for doctype, field in APPROVAL_DOCTYPES.items():
		name = workflow_name(doctype)
		workflow = (
			frappe.get_doc("Workflow", name)
			if frappe.db.exists("Workflow", name)
			else frappe.new_doc("Workflow")
		)
		workflow.update(
			{
				"workflow_name": name,
				"document_type": doctype,
				"workflow_state_field": "workflow_state",
				"is_active": settings.get(field),
				"send_email_alert": 0,
				"override_status": 0,
			}
		)
		workflow.set("states", get_states(doctype))
		workflow.set("transitions", get_transitions_rows(doctype, settings.allow_self_approval))
		workflow.flags.ignore_permissions = True
		workflow.save()


def get_states(doctype: str) -> list[dict]:
	submittable = frappe.get_meta(doctype).is_submittable
	states = [
		(DRAFT, 0, "Accounts Manager"),
		(PENDING_GM, 0, "General Manager"),
		(APPROVED, 1 if submittable else 0, "General Manager"),
		(REJECTED, 0, "Accounts Manager"),
	]
	if submittable:
		states.append((CANCELLED, 2, "Accounts Manager"))
	return [{"state": s, "doc_status": str(d), "allow_edit": role} for s, d, role in states]


def get_transitions_rows(doctype: str, allow_self_approval: int) -> list[dict]:
	rows = []
	for role in ("Accounts Manager", "General Manager"):
		rows.append((DRAFT, SEND, PENDING_GM, role))
		rows.append((REJECTED, RESUBMIT, PENDING_GM, role))
	rows += [
		(PENDING_GM, APPROVE, APPROVED, "General Manager"),
		(PENDING_GM, REJECT, REJECTED, "General Manager"),
	]
	if doctype == "Project":
		rows.append((APPROVED, REVISE, DRAFT, "Accounts Manager"))
		rows.append((APPROVED, REVISE, DRAFT, "General Manager"))
	return [
		{
			"state": state,
			"action": action,
			"next_state": next_state,
			"allowed": role,
			# only approving one's own document is restricted
			"allow_self_approval": 1 if action != APPROVE else allow_self_approval,
		}
		for state, action, next_state, role in rows
	]


def sync_workflows(settings):
	"""Turn the workflows on or off and apply the self-approval rule from Spend Settings."""
	for doctype, field in APPROVAL_DOCTYPES.items():
		name = workflow_name(doctype)
		if not frappe.db.exists("Workflow", name):
			continue
		workflow = frappe.get_doc("Workflow", name)
		before = workflow.as_dict()
		workflow.is_active = settings.get(field)
		for row in workflow.transitions:
			if row.action == APPROVE:
				row.allow_self_approval = settings.allow_self_approval
		if workflow.as_dict() == before:
			continue
		workflow.flags.ignore_permissions = True
		workflow.save()


def apply_settings():
	"""after_sync / after_migrate: the workflow fixtures overwrite the switches, so reapply them."""
	sync_workflows(frappe.get_single("Spend Settings"))


# ---------------------------------------------------------------- actions


def get_approval_info(doc) -> dict | None:
	"""State and the actions the current user may take."""
	if not is_approval_required(doc.doctype):
		return None
	actions = []
	if not doc.is_new() and doc.docstatus == 0:
		for transition in get_transitions(doc):
			if has_approval_access(frappe.session.user, doc, transition) and transition.action not in actions:
				actions.append(transition.action)
	return {
		"state": doc.get("workflow_state") or DRAFT,
		"actions": actions,
	}


@frappe.whitelist(methods=["POST"])
def apply_action(doctype: str, name: str, action: str, reason: str | None = None) -> dict:
	"""Run a workflow action. Rejecting needs a reason, which is kept as a comment."""
	from spend.api import check_app_permission

	check_app_permission()
	if doctype not in APPROVAL_DOCTYPES:
		frappe.throw(_("{0} does not use approvals").format(doctype))
	reason = (reason or "").strip()
	if action == REJECT and not reason:
		frappe.throw(_("Give a reason for rejecting"))

	frappe.flags.approval_reason = reason
	try:
		doc = apply_workflow(frappe.get_doc(doctype, name), action)
	finally:
		frappe.flags.approval_reason = None
	if reason:
		doc.add_comment("Comment", _("{0}: {1}").format(_(action), reason))
	return {"name": doc.name, "workflow_state": doc.workflow_state, "docstatus": doc.docstatus}


@frappe.whitelist()
def get_approval(doctype: str, name: str) -> dict | None:
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	return get_approval_info(doc)


@frappe.whitelist()
def get_pending_approvals(company: str | None = None) -> list[dict]:
	"""Documents waiting for an approval the current user can give."""
	from spend.api import check_app_permission

	check_app_permission()
	if "General Manager" not in frappe.get_roles():
		return []

	rows = []
	for doctype in get_active_approvals():
		if not frappe.has_permission(doctype, "read"):
			continue
		filters = {"workflow_state": PENDING_GM, "docstatus": 0}
		if company:
			filters["company"] = company
		for doc in frappe.get_list(
			doctype, filters=filters, fields=["name"], order_by="modified asc", limit=200
		):
			doc = frappe.get_doc(doctype, doc.name)
			info = get_approval_info(doc)
			if not info or APPROVE not in info["actions"]:
				continue
			rows.append({**describe(doc), "state": doc.workflow_state, "modified": doc.modified})
	return sorted(rows, key=lambda r: r["modified"])


def describe(doc) -> dict:
	"""A short title, amount and app route for a document under approval."""
	from spend.spend.amendment import get_amendment_note

	title, amount = {
		"Purchase Invoice": lambda: (doc.supplier, doc.grand_total),
		"Supplier Payment": lambda: (doc.supplier, doc.paid_amount),
		"Journal Entry": lambda: (doc.title, doc.total_debit),
		"Recurring Payment": lambda: (doc.title, doc.total_amount),
		"Budget": lambda: (f"{doc.cost_center} · {doc.fiscal_year}", doc.total_budget),
		"Project": lambda: (doc.project_name, doc.budget_amount),
	}[doc.doctype]()
	return {
		"doctype": doc.doctype,
		"name": doc.name,
		"title": title or doc.name,
		"amount": flt(amount),
		"currency": doc.get("currency"),
		"company": doc.get("company"),
		"owner": doc.owner,
		"owner_name": frappe.utils.get_fullname(doc.owner),
		"route": get_app_route(doc.doctype, doc.name),
		"note": get_amendment_note(doc),
	}


APP_ROUTES = {
	"Purchase Invoice": "bills",
	"Supplier Payment": "payments",
	"Journal Entry": "entries",
	"Recurring Payment": "recurring",
	"Budget": "budgets",
	"Project": "projects",
	"Asset": "assets",
	"Supplier": "suppliers",
	"Item": "items",
	"Task": "tasks",
}


def get_app_route(doctype: str, name: str) -> str | None:
	base = APP_ROUTES.get(doctype)
	return f"/spend/{base}/{name}" if base else None
