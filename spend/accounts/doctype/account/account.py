# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cint
from frappe.utils.nestedset import NestedSet

from spend.spend.accounting import get_balance

REPORT_TYPE = {
	"Asset": "Balance Sheet",
	"Liability": "Balance Sheet",
	"Equity": "Balance Sheet",
	"Income": "Profit and Loss",
	"Expense": "Profit and Loss",
}

# account_type -> root types it may be used with
ACCOUNT_TYPE_ROOTS = {
	"Fixed Asset": ("Asset",),
	"Accumulated Depreciation": ("Asset",),
	"Bank": ("Asset",),
	"Cash": ("Asset",),
	"Receivable": ("Asset",),
	"Payable": ("Liability",),
	"Depreciation": ("Expense",),
	"Expense Account": ("Expense",),
	"Cost of Goods Sold": ("Expense",),
	"Income Account": ("Income",),
	"Equity": ("Equity",),
}


class Account(NestedSet):
	nsm_parent_field = "parent_account"

	def autoname(self):
		self.name = get_account_name(self.account_name, self.company)

	def validate(self):
		self.validate_parent()
		self.validate_account_number()
		self.set_root_and_report_type()
		self.validate_account_type()
		self.validate_group_change()
		self.account_currency = frappe.get_cached_value("Company", self.company, "default_currency")

	def validate_parent(self):
		if not self.parent_account:
			if not self.is_group:
				frappe.throw(_("Root account {0} must be a group").format(frappe.bold(self.account_name)))
			if not self.root_type:
				frappe.throw(
					_("Root Type is mandatory for root account {0}").format(frappe.bold(self.account_name))
				)
			return

		if self.parent_account == self.name:
			frappe.throw(_("An account cannot be its own parent"))
		parent = frappe.db.get_value("Account", self.parent_account, ["company", "is_group"], as_dict=True)
		if not parent:
			frappe.throw(_("Parent Account {0} does not exist").format(self.parent_account))
		if parent.company != self.company:
			frappe.throw(
				_("Parent Account {0} does not belong to Company {1}").format(
					frappe.bold(self.parent_account), frappe.bold(self.company)
				)
			)
		if not parent.is_group:
			frappe.throw(_("Parent Account {0} must be a group").format(frappe.bold(self.parent_account)))

	def validate_account_number(self):
		self.account_number = (self.account_number or "").strip() or None
		if not self.account_number:
			return
		duplicate = frappe.db.get_value(
			"Account",
			{"company": self.company, "account_number": self.account_number, "name": ("!=", self.name)},
		)
		if duplicate:
			frappe.throw(
				_("Account Number {0} is already used by {1}").format(
					frappe.bold(self.account_number), frappe.bold(duplicate)
				),
				frappe.DuplicateEntryError,
			)

	def set_root_and_report_type(self):
		if self.parent_account:
			self.root_type = frappe.db.get_value("Account", self.parent_account, "root_type")
		self.report_type = REPORT_TYPE.get(self.root_type)

	def validate_account_type(self):
		roots = ACCOUNT_TYPE_ROOTS.get(self.account_type)
		if roots and self.root_type not in roots:
			frappe.throw(
				_("Account Type {0} can only be used with Root Type {1}").format(
					frappe.bold(self.account_type), " / ".join(roots)
				)
			)

	def validate_group_change(self):
		if self.is_new():
			return
		before = self.get_doc_before_save()
		if not before:
			return
		if cint(self.is_group) and not before.is_group and has_gl_entries(self.name):
			frappe.throw(_("Account with ledger entries cannot be converted to a group"))
		if before.root_type != self.root_type and has_gl_entries(self.name):
			frappe.throw(_("Root Type cannot change for an account with ledger entries"))

	def on_update(self):
		super().on_update()
		# children follow the root type of their parent
		if self.is_group and not self.is_new():
			descendants = frappe.get_all(
				"Account", filters={"lft": (">", self.lft), "rgt": ("<", self.rgt)}, pluck="name"
			)
			if descendants:
				frappe.db.set_value(
					"Account",
					{"name": ("in", descendants)},
					{"root_type": self.root_type, "report_type": self.report_type},
					update_modified=False,
				)

	def on_trash(self):
		if has_gl_entries(self.name):
			frappe.throw(
				_("Account {0} has ledger entries and cannot be deleted").format(frappe.bold(self.name))
			)
		super().on_trash(allow_root_deletion=True)

	def before_rename(self, old, new, merge=False):
		super().before_rename(old, new, merge)
		if merge and frappe.db.get_value("Account", new, "company") != self.company:
			frappe.throw(_("Accounts of different companies cannot be merged"))


def get_account_name(account_name: str, company: str) -> str:
	abbr = frappe.get_cached_value("Company", company, "abbr")
	return f"{account_name.strip()} - {abbr}"


def has_gl_entries(account: str) -> bool:
	return bool(frappe.db.exists("GL Entry", {"account": account}))


@frappe.whitelist()
def get_children(
	doctype: str, parent: str | None = None, company: str | None = None, is_root=False, **kwargs
):
	"""Tree view loader: root nodes are a company's root accounts."""
	if parent in (None, "", company, "All Accounts") or cint(is_root):
		parent = ""
	filters = {"parent_account": parent or ("is", "not set")}
	if company:
		filters["company"] = company
	accounts = frappe.get_list(
		"Account",
		filters=filters,
		fields=[
			"name as value",
			"account_name as title",
			"account_number",
			"is_group as expandable",
			"root_type",
			"account_type",
			"account_currency",
		],
		order_by="lft",
	)
	for account in accounts:
		account["balance"] = get_balance(account=account["value"])
	return accounts


@frappe.whitelist()
def get_account_balance(account: str, date: str | None = None) -> float:
	frappe.has_permission("Account", "read", account, throw=True)
	return get_balance(account=account, to_date=date)
