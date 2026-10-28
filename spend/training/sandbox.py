"""The training company: where trainees practise on the real Spend pages.

There is one shared company with Is Training checked. A scenario's Sample Data is
created in it when missing, and a trainer can wipe its documents with
`reset_training_data`, so real ledgers never see training entries.
"""

import json

import frappe
from frappe import _

TRAINING_COMPANY = "Spend Training"
TRAINING_ABBR = "TRN"

# what a scenario's Sample Data may create; all are master data, nothing posts to the ledger
SEEDABLE_DOCTYPES = (
	"Supplier",
	"Item",
	"Item Group",
	"UOM",
	"Cost Center",
	"Expense Category",
	"Project",
)

# the order to cancel and delete in: documents that point at others go first
RESETTABLE_DOCTYPES = (
	"Supplier Payment",
	"Journal Entry",
	"Asset Depreciation Schedule",
	"Asset",
	"Purchase Invoice",
	"Recurring Payment",
	"Budget",
	"Task",
	"Project",
	"Expense Category",
)


def get_training_company() -> str | None:
	return frappe.db.get_value("Company", {"is_training": 1}, "name", order_by="creation asc")


def ensure_training_company() -> str:
	"""The training company, created with the standard chart of accounts on first use."""
	if company := get_training_company():
		return company
	currency = (
		frappe.db.get_value("Company", {"is_training": 0}, "default_currency", order_by="creation asc")
		or frappe.db.get_single_value("System Settings", "currency")
		or "INR"
	)
	company = frappe.get_doc(
		{
			"doctype": "Company",
			"company_name": TRAINING_COMPANY,
			"abbr": TRAINING_ABBR,
			"default_currency": currency,
			"create_default_accounts": 1,
			"is_training": 1,
		}
	)
	company.insert(ignore_permissions=True)
	return company.name


def ensure_training_budget(company: str):
	"""Expenses are booked only to budgeted accounts, so the training company gets an open
	Budget for this year on all its expense accounts."""
	from spend.spend.accounting import get_fiscal_year
	from spend.spend.approval import APPROVED, is_approval_required

	fiscal_year = get_fiscal_year(frappe.utils.today(), throw=False)
	cost_center = frappe.db.get_value("Cost Center", {"company": company, "parent_cost_center": ("is", "not set")})
	if not (fiscal_year and cost_center):
		return
	if frappe.db.exists(
		"Budget", {"company": company, "cost_center": cost_center, "fiscal_year": fiscal_year, "docstatus": 1}
	):
		return
	accounts = frappe.get_all(
		"Account", filters={"company": company, "root_type": "Expense", "is_group": 0}, pluck="name"
	)
	budget = frappe.get_doc(
		{
			"doctype": "Budget",
			"company": company,
			"fiscal_year": fiscal_year,
			"cost_center": cost_center,
			"action_if_exceeded": "Ignore",
			"accounts": [{"account": account, "budget_amount": 10**9} for account in accounts],
		}
	)
	budget.flags.ignore_permissions = True
	budget.insert()
	if is_approval_required("Budget"):
		budget.db_set("workflow_state", APPROVED)  # set up by the system, not a trainee's budget
	budget.submit()


def apply_seed_data(seed: dict, company: str):
	"""Create each Sample Data record that does not exist yet. `{company}` in a value is
	replaced with the training company, and a doctype with a Company field gets it filled in."""
	for doctype, records in seed.items():
		if doctype not in SEEDABLE_DOCTYPES:
			continue
		meta = frappe.get_meta(doctype)
		for record in records:
			values = {
				key: value.replace("{company}", company) if isinstance(value, str) else value
				for key, value in record.items()
			}
			if meta.has_field("company"):
				values.setdefault("company", company)
			if not seed_record_exists(doctype, meta, values):
				frappe.get_doc({"doctype": doctype, **values}).insert(ignore_permissions=True)


def seed_record_exists(doctype: str, meta, values: dict) -> bool:
	autoname = meta.autoname or ""
	if autoname.startswith("field:"):
		name = values.get(autoname.removeprefix("field:"))
		return bool(name and frappe.db.exists(doctype, name))
	filters = {key: value for key, value in values.items() if not isinstance(value, list | dict)}
	return bool(frappe.db.exists(doctype, filters))


def parse_seed(raw: str | None) -> dict:
	if not raw or not raw.strip():
		return {}
	try:
		seed = json.loads(raw)
	except ValueError:
		return {}
	return seed if isinstance(seed, dict) else {}


def reset_company(company: str) -> dict:
	"""Cancel and delete every training document of the company, then its ledger entries.

	Documents that still fail after a few passes (for example a link this list does
	not know about) are reported, not raised, so one bad record doesn't block the rest."""
	deleted = 0
	failed: dict[tuple[str, str], str] = {}
	for _pass in range(3):
		failed.clear()
		for doctype in RESETTABLE_DOCTYPES:
			for name in frappe.get_all(doctype, filters={"company": company}, pluck="name"):
				if remove_document(doctype, name, failed):
					deleted += 1
		if not failed:
			break
	if not failed:
		frappe.db.delete("GL Entry", {"company": company})
	return {
		"deleted": deleted,
		"failed": [{"doctype": dt, "name": name, "error": error} for (dt, name), error in failed.items()],
	}


def remove_document(doctype: str, name: str, failed: dict) -> bool:
	frappe.db.savepoint("training_reset")
	try:
		doc = frappe.get_doc(doctype, name)
		doc.flags.ignore_permissions = True
		doc.flags.ignore_links = True
		if doc.docstatus == 1:
			doc.cancel()
		frappe.delete_doc(doctype, name, force=1, ignore_permissions=True, ignore_on_trash=True)
		return True
	except Exception as e:
		frappe.db.rollback(save_point="training_reset")
		frappe.clear_messages()
		failed[(doctype, name)] = str(e) or e.__class__.__name__
		return False


def validate_company(doc, method=None):
	"""Company.validate: the training company stays one, while it has documents."""
	before = doc.get_doc_before_save()
	if not before or not before.is_training or doc.is_training:
		return
	for doctype in RESETTABLE_DOCTYPES:
		if frappe.db.exists(doctype, {"company": doc.name}):
			frappe.throw(
				_("Reset the training data before unchecking Is Training: {0} records exist").format(_(doctype))
			)
