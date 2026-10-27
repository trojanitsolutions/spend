# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cint
from frappe.utils.nestedset import NestedSet


class CostCenter(NestedSet):
	nsm_parent_field = "parent_cost_center"

	def autoname(self):
		abbr = frappe.get_cached_value("Company", self.company, "abbr")
		self.name = f"{self.cost_center_name.strip()} - {abbr}"

	def validate(self):
		self.validate_parent()
		self.validate_group_change()

	def validate_parent(self):
		if not self.parent_cost_center:
			if not self.is_group:
				frappe.throw(
					_("Root cost center {0} must be a group").format(frappe.bold(self.cost_center_name))
				)
			return
		if self.parent_cost_center == self.name:
			frappe.throw(_("A cost center cannot be its own parent"))
		parent = frappe.db.get_value(
			"Cost Center", self.parent_cost_center, ["company", "is_group"], as_dict=True
		)
		if not parent:
			frappe.throw(_("Parent Cost Center {0} does not exist").format(self.parent_cost_center))
		if parent.company != self.company:
			frappe.throw(
				_("Parent Cost Center {0} does not belong to Company {1}").format(
					frappe.bold(self.parent_cost_center), frappe.bold(self.company)
				)
			)
		if not parent.is_group:
			frappe.throw(
				_("Parent Cost Center {0} must be a group").format(frappe.bold(self.parent_cost_center))
			)

	def validate_group_change(self):
		if self.is_new() or not cint(self.is_group):
			return
		before = self.get_doc_before_save()
		if before and not before.is_group and frappe.db.exists("GL Entry", {"cost_center": self.name}):
			frappe.throw(_("Cost Center with ledger entries cannot be converted to a group"))

	def on_trash(self):
		if frappe.db.exists("GL Entry", {"cost_center": self.name}):
			frappe.throw(
				_("Cost Center {0} has ledger entries and cannot be deleted").format(frappe.bold(self.name))
			)
		super().on_trash(allow_root_deletion=True)


@frappe.whitelist()
def get_children(
	doctype: str, parent: str | None = None, company: str | None = None, is_root=False, **kwargs
):
	if parent in (None, "", company, "All Cost Centers") or cint(is_root):
		parent = ""
	filters = {"parent_cost_center": parent or ("is", "not set")}
	if company:
		filters["company"] = company
	return frappe.get_list(
		"Cost Center",
		filters=filters,
		fields=["name as value", "cost_center_name as title", "is_group as expandable"],
		order_by="lft",
	)
