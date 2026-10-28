# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from spend.spend.accounting import GL_PRECISION
from spend.spend.depreciation import calculate_schedule, get_periodic_rate, implied_annual_rate


class DuplicateScheduleError(frappe.ValidationError):
	pass


class AssetDepreciationSchedule(Document):
	"""Generated from an Asset. A draft follows the asset while it is a draft;
	it is submitted with the asset and cancelled with it."""

	def validate(self):
		self.validate_single_schedule()
		self.total_depreciation = flt(sum(flt(r.depreciation_amount) for r in self.schedules), GL_PRECISION)

	def validate_single_schedule(self):
		other = frappe.db.get_value(
			"Asset Depreciation Schedule",
			{"asset": self.asset, "docstatus": ("<", 2), "name": ("!=", self.name or "")},
		)
		if other:
			frappe.throw(
				_("Asset {0} already has depreciation schedule {1}").format(
					frappe.bold(self.asset), frappe.bold(other)
				),
				DuplicateScheduleError,
			)

	def before_submit(self):
		if not self.schedules:
			frappe.throw(_("Depreciation schedule has no rows"))
		self.status = "Active"

	def before_cancel(self):
		self.ignore_linked_doctypes = ("Asset", "Journal Entry")
		posted = [r.journal_entry for r in self.schedules if r.journal_entry]
		if posted:
			frappe.throw(_("Cancel the posted depreciation entries first: {0}").format(", ".join(posted)))

	def on_cancel(self):
		self.db_set("status", "Cancelled")

	def set_from_asset(self, asset):
		self.asset = asset.name
		self.company = asset.company
		self.cost_center = asset.cost_center
		for field in (
			"depreciation_method",
			"frequency_of_depreciation",
			"total_number_of_depreciations",
			"depreciation_start_date",
			"gross_purchase_amount",
			"salvage_value",
		):
			self.set(field, asset.get(field))

		periodic_rate = get_periodic_rate(
			asset.depreciation_method,
			asset.gross_purchase_amount,
			asset.salvage_value,
			asset.total_number_of_depreciations,
			asset.frequency_of_depreciation,
			asset.rate_of_depreciation,
		)
		self.rate_of_depreciation = asset.rate_of_depreciation or implied_annual_rate(
			periodic_rate, asset.frequency_of_depreciation
		)
		self.schedules = []
		for row in calculate_schedule(
			cost=asset.gross_purchase_amount,
			salvage=asset.salvage_value,
			method=asset.depreciation_method,
			frequency=asset.frequency_of_depreciation,
			number_of_depreciations=asset.total_number_of_depreciations,
			start_date=asset.depreciation_start_date,
			annual_rate=asset.rate_of_depreciation,
		):
			self.append("schedules", row)


@frappe.whitelist()
def post_depreciation(schedule: str, date: str | None = None) -> list[str]:
	from spend.spend.depreciation import post_due_depreciation

	asset = frappe.db.get_value("Asset Depreciation Schedule", schedule, "asset")
	return post_due_depreciation(asset=asset, date=date)
