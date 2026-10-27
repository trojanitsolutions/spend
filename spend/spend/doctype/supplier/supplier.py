# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from spend.spend.accounting import GL_PRECISION, get_balance


class Supplier(Document):
	def validate(self):
		self.supplier_name = (self.supplier_name or "").strip()

	def on_trash(self):
		for doctype in ("Purchase Invoice", "Supplier Payment"):
			if frappe.db.exists(doctype, {"supplier": self.name}):
				frappe.throw(
					_("Cannot delete Supplier {0} because {1} records exist").format(
						frappe.bold(self.name), _(doctype)
					)
				)
		if frappe.db.exists("GL Entry", {"party_type": "Supplier", "party": self.name}):
			frappe.throw(_("Cannot delete Supplier {0} because it has ledger entries").format(self.name))


def get_supplier_outstanding(supplier: str, company: str | None = None) -> float:
	"""Amount owed to the supplier: credits less debits on their payable ledger rows."""
	return flt(-get_balance(party_type="Supplier", party=supplier, company=company), GL_PRECISION)


@frappe.whitelist()
def get_outstanding(supplier: str, company: str | None = None) -> float:
	frappe.has_permission("Supplier", "read", supplier, throw=True)
	return get_supplier_outstanding(supplier, company)
