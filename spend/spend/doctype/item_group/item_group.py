# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils.nestedset import NestedSet, get_ancestors_of

from spend.spend.accounting import validate_ledger_account
from spend.spend.doctype.journal_entry.journal_entry import validate_cost_center

ROOT = "All Item Groups"


class ItemGroup(NestedSet):
	nsm_parent_field = "parent_item_group"

	def validate(self):
		self.item_group_name = (self.item_group_name or "").strip()
		if not self.parent_item_group and self.name != ROOT and frappe.db.exists("Item Group", ROOT):
			self.parent_item_group = ROOT
		if self.parent_item_group and not frappe.db.get_value(
			"Item Group", self.parent_item_group, "is_group"
		):
			frappe.throw(
				_("Parent Item Group {0} must be a group").format(frappe.bold(self.parent_item_group))
			)
		self.validate_ledger()
		self.validate_defaults()

	def validate_defaults(self):
		companies = set()
		for row in self.item_group_defaults:
			if row.company in companies:
				frappe.throw(_("Row {0}: Company {1} is repeated").format(row.idx, frappe.bold(row.company)))
			companies.add(row.company)
			if row.expense_account:
				label = _("Row {0}: Default Expense Account").format(row.idx)
				validate_ledger_account(row.expense_account, row.company, label, root_types=("Expense",))
			if row.buying_cost_center:
				validate_cost_center(row.buying_cost_center, row.company, row.idx)

	def on_update(self):
		super().on_update()
		self.validate_one_root()

	def on_trash(self):
		if self.name == ROOT:
			frappe.throw(_("{0} is the root and cannot be deleted").format(frappe.bold(ROOT)))
		if frappe.db.exists("Item", {"item_group": self.name}):
			frappe.throw(
				_("Cannot delete Item Group {0} because items use it").format(frappe.bold(self.name))
			)
		super().on_trash()


def get_item_group_defaults(item_group: str | None, company: str) -> dict:
	"""Expense account and cost center of the closest group, walking up the tree, that sets them."""
	found = {}
	for group in filter(None, [item_group, *get_ancestors_of("Item Group", item_group or "")]):
		row = frappe.db.get_value(
			"Item Default",
			{"parenttype": "Item Group", "parent": group, "company": company},
			["expense_account", "buying_cost_center"],
			as_dict=True,
		)
		for field, value in (row or {}).items():
			if value and not found.get(field):
				found[field] = value
	return found


def make_root():
	if not frappe.db.exists("Item Group", ROOT):
		frappe.get_doc({"doctype": "Item Group", "item_group_name": ROOT, "is_group": 1}).insert(
			ignore_permissions=True
		)
