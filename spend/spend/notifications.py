# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

"""In-app (Notification Log) and email notifications for approvals, budgets, bills and recurring payments."""

import frappe
from frappe import _
from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
from frappe.desk.doctype.notification_settings.notification_settings import is_email_notifications_enabled
from frappe.utils import add_days, flt, fmt_money, get_url, getdate, nowdate, strip_html

from spend.spend.accounting import GL_PRECISION, get_balance, get_subtree
from spend.spend.approval import (
	APPROVED,
	PENDING_GM,
	PENDING_MANAGER,
	REJECTED,
	describe,
	get_app_route,
	is_approval_required,
)

APPROVAL, BUDGET_ALERT, BILL_REMINDER, RECURRING = (
	"Approval",
	"Budget Alert",
	"Bill Reminder",
	"Recurring Payment",
)
NOTIFICATION_TYPES = (APPROVAL, BUDGET_ALERT, BILL_REMINDER, RECURRING)


def setup_notification_types():
	for name in NOTIFICATION_TYPES:
		if not frappe.db.exists("Notification Type", name):
			frappe.get_doc({"doctype": "Notification Type", "type_name": name, "enabled": 1}).insert(
				ignore_permissions=True
			)


def get_setting(field: str):
	return frappe.db.get_single_value("Spend Settings", field, cache=False)


def users_with_role(*roles: str) -> set[str]:
	user = frappe.qb.DocType("User")
	has_role = frappe.qb.DocType("Has Role")
	return set(
		frappe.qb.from_(user)
		.join(has_role)
		.on((has_role.parent == user.name) & (has_role.parenttype == "User"))
		.select(user.name)
		.distinct()
		.where(
			(has_role.role.isin(roles))
			& (user.enabled == 1)
			& (user.user_type == "System User")
			& (user.name.notin(["Administrator", "Guest"]))
		)
		.run(pluck=True)
	)


def notify(users, subject: str, doc=None, message: str = "", notification_type: str = APPROVAL, link=None):
	"""Bell notification for each user (except the one acting), plus email when it is turned on."""
	users = {u for u in users or () if u and u not in (frappe.session.user, "Guest")}
	if not users:
		return
	link = link or (get_app_route(doc.doctype, doc.name) if doc else None)
	enqueue_create_notification(
		list(users),
		{
			"type": notification_type,
			"subject": subject,
			"email_content": message,
			"document_type": doc.doctype if doc else None,
			"document_name": doc.name if doc else None,
			"from_user": frappe.session.user,
			"link": link,
		},
	)
	if get_setting("send_email"):
		send_email(users, subject, message, link)


def send_email(users: set[str], subject: str, message: str, link: str | None):
	recipients = [
		email
		for name, email in frappe.get_all(
			"User",
			filters={"name": ("in", list(users)), "enabled": 1},
			fields=["name", "email"],
			as_list=True,
		)
		if email and is_email_notifications_enabled(name)
	]
	if not recipients:
		return
	try:
		frappe.sendmail(
			recipients=recipients,
			subject=strip_html(subject),
			template="new_notification",
			args={
				"body_content": subject,
				"description": message,
				"doc_link": get_url(link) if link else None,
			},
			header=[_("Spend"), "orange"],
		)
	except frappe.OutgoingEmailError:
		frappe.log_error(title=_("Spend notification email failed"))


def amount_text(amount, currency=None) -> str:
	return fmt_money(flt(amount), currency=currency)


# ---------------------------------------------------------------- approvals


def on_approval_change(doc, method=None):
	"""doc_events on_change: tell the next approvers, or the preparer about the outcome."""
	before = doc.get_doc_before_save()
	old, new = before.get("workflow_state") if before else None, doc.get("workflow_state")
	if not new or old == new or not is_approval_required(doc.doctype):
		return

	info = describe(doc)
	label = _("{0} {1}").format(_(doc.doctype), doc.name)
	what = _("{0} ({1}, {2})").format(label, info["title"], amount_text(info["amount"], info["currency"]))
	actor = frappe.utils.get_fullname(frappe.session.user)
	note = f" · {info['note']}" if info["note"] else ""

	if new == PENDING_MANAGER:
		notify(
			users_with_role("Accounts Manager"),
			_("{0} needs your approval").format(what),
			doc,
			_("Sent by {0}").format(actor) + note,
		)
	elif new == PENDING_GM:
		notify(
			users_with_role("General Manager"),
			_("{0} needs your approval").format(what),
			doc,
			_("Approved by {0} (Accounts Manager)").format(actor) + note,
		)
		notify(
			[doc.owner],
			_("{0} was approved by {1} and is with the General Manager").format(label, actor),
			doc,
		)
	elif new == APPROVED:
		posted = _(" and posted") if doc.docstatus == 1 else ""
		notify([doc.owner], _("{0} was approved by {1}{2}").format(label, actor, posted), doc)
	elif new == REJECTED:
		reason = frappe.flags.approval_reason or ""
		notify(
			[doc.owner],
			_("{0} was rejected by {1}").format(label, actor),
			doc,
			_("Reason: {0}").format(reason) if reason else "",
		)


def notify_cancelled(doc, consequence: str):
	"""A cancelled budget or recurring payment changes what is checked or paid, so managers hear of it."""
	label = _("{0} {1}").format(_(doc.doctype), doc.name)
	notify(
		{doc.owner, *users_with_role("Accounts Manager", "General Manager")},
		_("{0} was cancelled by {1}").format(label, frappe.utils.get_fullname(frappe.session.user)),
		doc,
		consequence,
	)


# ---------------------------------------------------------------- budgets


def notify_budget_usage(doc, lines: list[tuple]):
	"""Alert when this voucher takes a project or cost center budget past the threshold or its limit.

	`lines` are (account, cost_center, project, amount) tuples of the posted voucher.
	Usage before the voucher is compared with usage after it, so each crossing alerts once.
	"""
	threshold = flt(get_setting("budget_alert_threshold"))
	exceeded = get_setting("notify_budget_exceeded")
	if not threshold and not exceeded:
		return
	expense = [
		(account, cost_center, project, flt(amount))
		for account, cost_center, project, amount in lines
		if flt(amount) > 0 and frappe.db.get_value("Account", account, "root_type") == "Expense"
	]
	if not expense:
		return
	try:
		alerts = get_project_alerts(expense, threshold, exceeded) + get_budget_alerts(
			doc, expense, threshold, exceeded
		)
	except Exception:
		frappe.log_error(title=_("Budget alert failed for {0}").format(doc.name))
		return
	recipients = users_with_role("Accounts Manager", "General Manager")
	for subject, target in alerts:
		notify(recipients, subject, target, _("After {0} {1}").format(_(doc.doctype), doc.name), BUDGET_ALERT)


def crossing(before: float, after: float, limit: float, threshold: float, exceeded) -> str | None:
	if limit <= 0:
		return None
	if exceeded and before <= limit < after:
		return "exceeded"
	if threshold and before < limit * threshold / 100 <= after:
		return "threshold"
	return None


def alert_subject(level: str, scope: str, after: float, limit: float, currency) -> str:
	used = flt(after / limit * 100, 1)
	if level == "exceeded":
		return _("{0} is over budget: {1} spent of {2}").format(
			scope, amount_text(after, currency), amount_text(limit, currency)
		)
	return _("{0} has used {1}% of its budget ({2} of {3})").format(
		scope, used, amount_text(after, currency), amount_text(limit, currency)
	)


def get_project_alerts(lines, threshold, exceeded) -> list[tuple]:
	from spend.spend.doctype.project.project import get_project_spent

	alerts = []
	for project_name in {project for _a, _c, project, _amt in lines if project}:
		project = frappe.get_doc("Project", project_name)
		amounts = [(account, amount) for account, _c, p, amount in lines if p == project_name]
		checks = [(None, flt(project.budget_amount), sum(a for _acc, a in amounts))]
		for row in project.budget_accounts:
			covered = set(get_subtree("Account", row.account))
			checks.append(
				(row.account, flt(row.budget_amount), sum(a for acc, a in amounts if acc in covered))
			)
		for account, limit, amount in checks:
			if amount <= 0:
				continue
			after = get_project_spent(project.name, account)
			level = crossing(flt(after - amount, GL_PRECISION), after, limit, threshold, exceeded)
			if level:
				scope = (
					_("Project {0}, account {1}").format(project.project_name, account)
					if account
					else _("Project {0}").format(project.project_name)
				)
				alerts.append((alert_subject(level, scope, after, limit, project.currency), project))
	return alerts


def get_budget_alerts(doc, lines, threshold, exceeded) -> list[tuple]:
	from spend.spend.doctype.budget.budget import get_applicable_budgets

	alerts, seen = [], set()
	for account, cost_center, _p, _amt in lines:
		if not cost_center:
			continue
		for budget_name in get_applicable_budgets(doc, account, cost_center):
			if (budget_name, account) in seen:
				continue
			seen.add((budget_name, account))
			budget = frappe.get_doc("Budget", budget_name)
			limit = next(flt(r.budget_amount) for r in budget.accounts if r.account == account)
			covered = set(get_subtree("Cost Center", budget.cost_center))
			amount = sum(amt for acc, cc, _p, amt in lines if acc == account and cc in covered)
			start, end = frappe.db.get_value("Fiscal Year", budget.fiscal_year, ["start_date", "end_date"])
			after = get_balance(
				account=account,
				cost_center=budget.cost_center,
				company=budget.company,
				from_date=start,
				to_date=end,
			)
			level = crossing(flt(after - amount, GL_PRECISION), after, limit, threshold, exceeded)
			if level:
				scope = _("Budget {0} ({1}, {2})").format(budget.name, budget.cost_center, account)
				alerts.append((alert_subject(level, scope, after, limit, budget.currency), budget))
	return alerts


# ---------------------------------------------------------------- bills


def notify_bills_due():
	"""Daily digest of unpaid bills due soon or overdue, per company."""
	if not get_setting("notify_bills_due"):
		return
	today = getdate(nowdate())
	horizon = add_days(today, int(get_setting("bill_due_days") or 0))
	recipients = users_with_role("Accounts User", "Accounts Manager")
	for company, currency in frappe.get_all("Company", fields=["name", "default_currency"], as_list=True):
		subject = get_bills_due_subject(company, currency, today, horizon)
		if subject:
			notify(recipients, subject, notification_type=BILL_REMINDER, link="/spend/bills")


def get_bills_due_subject(company: str, currency: str, today, horizon) -> str | None:
	bills = frappe.get_all(
		"Purchase Invoice",
		filters={
			"company": company,
			"docstatus": 1,
			"outstanding_amount": (">", 0),
			"due_date": ("<=", horizon),
		},
		fields=["due_date", "outstanding_amount"],
	)
	overdue = [b for b in bills if getdate(b.due_date) < today]
	due = [b for b in bills if getdate(b.due_date) >= today]
	if not bills:
		return None
	parts = []
	if due:
		parts.append(
			_("{0} due by {1} ({2})").format(
				len(due),
				frappe.format(horizon, "Date"),
				amount_text(sum(b.outstanding_amount for b in due), currency),
			)
		)
	if overdue:
		parts.append(
			_("{0} overdue ({1})").format(
				len(overdue), amount_text(sum(b.outstanding_amount for b in overdue), currency)
			)
		)
	return _("{0}: bills to pay, {1}").format(company, ", ".join(parts))


# ---------------------------------------------------------------- recurring payments


def notify_recurring_posted(doc, entries: list[str]):
	if not entries or not get_setting("notify_recurring"):
		return
	amount = sum(
		flt(v)
		for v in frappe.get_all("Journal Entry", filters={"name": ("in", entries)}, pluck="total_debit")
	)
	notify(
		[doc.owner],
		_("{0}: {1} payment(s) of {2} posted").format(
			doc.title, len(entries), amount_text(amount, doc.currency)
		),
		doc,
		", ".join(entries),
		RECURRING,
	)


def notify_recurring_failed(name: str, error: str):
	if not get_setting("notify_recurring"):
		return
	doc = frappe.get_doc("Recurring Payment", name)
	notify(
		users_with_role("Accounts Manager") | {doc.owner},
		_("{0} ({1}): a payment could not be posted").format(doc.title, doc.name),
		doc,
		strip_html(error or "")[:500],
		RECURRING,
	)


# ---------------------------------------------------------------- the user's notifications


@frappe.whitelist()
def get_notifications(limit: int = 20, unread_only: int = 0) -> list[dict]:
	filters = {"for_user": frappe.session.user}
	if int(unread_only):
		filters["read"] = 0
	return frappe.get_all(
		"Notification Log",
		filters=filters,
		fields=[
			"name",
			"subject",
			"email_content",
			"type",
			"document_type",
			"document_name",
			"link",
			"read",
			"from_user",
			"creation",
		],
		order_by="creation desc",
		limit=min(int(limit), 200),
	)


@frappe.whitelist()
def get_counts(company: str | None = None) -> dict:
	"""Unread notifications and documents waiting at an approval stage the user's roles can act on."""
	from spend.spend.approval import get_active_approvals

	roles = set(frappe.get_roles())
	states = [
		state
		for state, role in ((PENDING_MANAGER, "Accounts Manager"), (PENDING_GM, "General Manager"))
		if role in roles
	]
	pending = 0
	if states:
		for doctype in get_active_approvals():
			if not frappe.has_permission(doctype, "read"):
				continue
			filters = {"workflow_state": ("in", states), "docstatus": 0, "owner": ("!=", frappe.session.user)}
			if company:
				filters["company"] = company
			pending += len(frappe.get_list(doctype, filters=filters, pluck="name", limit=500))
	return {
		"unread": frappe.db.count("Notification Log", {"for_user": frappe.session.user, "read": 0}),
		"pending": pending,
	}


@frappe.whitelist(methods=["POST"])
def mark_read(names: list | str | None = None):
	"""Mark the given notifications, or all of them, as read for the current user."""
	log = frappe.qb.DocType("Notification Log")
	query = (
		frappe.qb.update(log).set(log.read, 1).where((log.for_user == frappe.session.user) & (log.read == 0))
	)
	if names:
		if isinstance(names, str):
			names = frappe.parse_json(names) if names.startswith("[") else [names]
		query = query.where(log.name.isin(list(names)))
	query.run()
