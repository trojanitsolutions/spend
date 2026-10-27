# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from spend.spend.accounting import validate_ledger_account


class ExpenseCategory(Document):
	def autoname(self):
		abbr = frappe.get_cached_value("Company", self.company, "abbr")
		self.name = f"{self.category_name.strip()} - {abbr}"

	def validate(self):
		validate_ledger_account(self.expense_account, self.company, _("Expense Account"), ["Expense"])
		if self.is_parent_category:
			self.parent_category = None
			self.validate_parent_change()
		else:
			self.validate_parent()

	def validate_parent(self):
		if not self.parent_category:
			frappe.throw(_("Pick a Parent Category, or check Parent Category to make this one a parent"))
		if self.parent_category == self.name:
			frappe.throw(_("A category cannot be its own parent"))
		parent = frappe.db.get_value(
			"Expense Category", self.parent_category, ["company", "is_parent_category"], as_dict=True
		)
		if not parent:
			frappe.throw(_("Expense Category {0} does not exist").format(self.parent_category))
		if parent.company != self.company:
			frappe.throw(
				_("Parent Category {0} does not belong to Company {1}").format(
					frappe.bold(self.parent_category), frappe.bold(self.company)
				)
			)
		if not parent.is_parent_category:
			frappe.throw(_("{0} is not a parent category").format(frappe.bold(self.parent_category)))
		if frappe.db.exists("Expense Category", {"parent_category": self.name}):
			frappe.throw(_("{0} has sub categories, so it must stay a parent").format(frappe.bold(self.name)))

	def validate_parent_change(self):
		"""A sub category already used on bookings stays a sub category."""
		before = self.get_doc_before_save()
		if before and not before.is_parent_category and is_used(self.name, "expense_sub_category"):
			frappe.throw(
				_("{0} is used as a sub category on bookings and cannot become a parent").format(
					frappe.bold(self.name)
				)
			)

	def on_trash(self):
		if frappe.db.exists("Expense Category", {"parent_category": self.name}):
			frappe.throw(_("Delete the sub categories of {0} first").format(frappe.bold(self.name)))


def is_used(category: str, fieldname: str) -> bool:
	return bool(frappe.db.exists("GL Entry", {fieldname: category}))


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_categories(doctype, txt, searchfield, start, page_len, filters):
	"""Parent categories, or with a `parent_category` filter the sub categories of that category.

	`filters.project` limits them to the categories picked on that project, when it has any.
	"""
	from spend.spend.expense_category import get_project_category_rows

	filters = frappe._dict(filters or {})
	sub_categories = "parent_category" in filters
	if sub_categories and not filters.parent_category:
		return []  # no category picked yet
	conditions = {"disabled": 0}
	if filters.company:
		conditions["company"] = filters.company
	if sub_categories:
		conditions["parent_category"] = filters.parent_category
	else:
		conditions["is_parent_category"] = 1

	rows = get_project_category_rows(filters.project) if filters.project else []
	if rows:
		if sub_categories:
			subs = {
				r.expense_sub_category or None for r in rows if r.expense_category == filters.parent_category
			}
			if None not in subs:  # the whole category is not on the project, only some sub categories
				conditions["name"] = ("in", list(subs))
		else:
			conditions["name"] = ("in", list({r.expense_category for r in rows}))

	return frappe.get_list(
		"Expense Category",
		filters=conditions,
		or_filters={"name": ("like", f"%{txt}%"), "category_name": ("like", f"%{txt}%")} if txt else None,
		fields=["name", "parent_category"],
		order_by="category_name",
		start=start,
		page_length=page_len,
		as_list=True,
	)
