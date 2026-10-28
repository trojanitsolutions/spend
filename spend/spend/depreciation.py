# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

"""Depreciation schedule maths and depreciation postings.

Straight Line
	depreciation per period = (cost - salvage) / number of periods
Written Down Value
	depreciation per period = opening book value x periodic rate, where
	periodic rate = 1 - (1 - annual rate) ^ (months per period / 12) when an annual rate is given,
	periodic rate = 1 - (salvage / cost) ^ (1 / number of periods) otherwise.

For both methods the last period takes whatever is left down to the salvage
value (this absorbs rounding), and no period ever takes the book value below
the salvage value. Number of periods = useful life in months / months per period.
"""

import frappe
from frappe import _
from frappe.utils import add_months, cint, flt, get_last_day, getdate, nowdate

from spend.spend.accounting import GL_PRECISION, get_balance

FREQUENCY_MONTHS = {"Monthly": 1, "Quarterly": 3, "Half-Yearly": 6, "Yearly": 12}
STRAIGHT_LINE = "Straight Line"
WRITTEN_DOWN_VALUE = "Written Down Value"


class DepreciationError(frappe.ValidationError):
	pass


# ---------------------------------------------------------------- schedule maths (pure)


def get_number_of_depreciations(useful_life_years: float, frequency: str) -> int:
	months = flt(useful_life_years) * 12
	periods = months / FREQUENCY_MONTHS[frequency]
	if periods < 1 or abs(periods - round(periods)) > 1e-6:
		frappe.throw(
			_("Useful life of {0} years does not divide into whole {1} periods").format(
				flt(useful_life_years), _(frequency).lower()
			),
			DepreciationError,
		)
	return round(periods)


def get_default_start_date(available_for_use_date, frequency: str):
	"""End of the first full period after the asset is available for use."""
	return get_last_day(add_months(getdate(available_for_use_date), FREQUENCY_MONTHS[frequency] - 1))


def get_schedule_dates(start_date, number_of_depreciations: int, frequency: str) -> list:
	start_date = getdate(start_date)
	month_end = start_date == get_last_day(start_date)
	step = FREQUENCY_MONTHS[frequency]
	dates = []
	for i in range(number_of_depreciations):
		date = add_months(start_date, i * step)
		dates.append(get_last_day(date) if month_end else getdate(date))
	return dates


def get_periodic_rate(
	method: str, cost: float, salvage: float, number_of_depreciations: int, frequency: str, annual_rate=None
) -> float:
	if method == STRAIGHT_LINE:
		return 1 / number_of_depreciations
	if flt(annual_rate):
		if not 0 < flt(annual_rate) < 100:
			frappe.throw(_("Rate of Depreciation must be between 0 and 100"), DepreciationError)
		return 1 - (1 - flt(annual_rate) / 100) ** (FREQUENCY_MONTHS[frequency] / 12)
	if flt(salvage) <= 0:
		frappe.throw(
			_("Written Down Value needs either a Rate of Depreciation or a Salvage Value above zero"),
			DepreciationError,
		)
	return 1 - (flt(salvage) / flt(cost)) ** (1 / number_of_depreciations)


def implied_annual_rate(periodic_rate: float, frequency: str) -> float:
	return flt((1 - (1 - periodic_rate) ** (12 / FREQUENCY_MONTHS[frequency])) * 100, 4)


def calculate_schedule(
	cost: float,
	salvage: float,
	method: str,
	frequency: str,
	number_of_depreciations: int,
	start_date,
	annual_rate=None,
	precision: int = GL_PRECISION,
) -> list[dict]:
	"""Return one row per period with opening/closing book value and accumulated depreciation."""
	cost, salvage = flt(cost, precision), flt(salvage, precision)
	if cost <= 0:
		frappe.throw(_("Gross Purchase Amount must be greater than zero"), DepreciationError)
	if salvage < 0 or salvage >= cost:
		frappe.throw(
			_("Salvage Value must be zero or more and less than the Gross Purchase Amount"), DepreciationError
		)
	if method not in (STRAIGHT_LINE, WRITTEN_DOWN_VALUE):
		frappe.throw(_("Unsupported depreciation method {0}").format(method), DepreciationError)

	n = cint(number_of_depreciations)
	rate = get_periodic_rate(method, cost, salvage, n, frequency, annual_rate)
	straight_line_amount = flt((cost - salvage) / n, precision)

	rows, book_value, accumulated = [], cost, 0.0
	for i, schedule_date in enumerate(get_schedule_dates(start_date, n, frequency)):
		opening = book_value
		depreciable = flt(opening - salvage, precision)
		if depreciable <= 0:
			break
		if i == n - 1:
			amount = depreciable
		elif method == STRAIGHT_LINE:
			amount = straight_line_amount
		else:
			amount = flt(opening * rate, precision)
		amount = flt(min(max(amount, 0), depreciable), precision)
		if amount <= 0:
			continue

		accumulated = flt(accumulated + amount, precision)
		book_value = flt(opening - amount, precision)
		rows.append(
			{
				"schedule_date": schedule_date,
				"opening_book_value": opening,
				"depreciation_amount": amount,
				"accumulated_depreciation_amount": accumulated,
				"closing_book_value": book_value,
			}
		)
	return rows


# ---------------------------------------------------------------- postings


def post_depreciation_entries_daily():
	"""Scheduler entry point: post all due depreciation, committing per asset."""
	for schedule in get_schedules_with_due_rows(nowdate()):
		try:
			make_depreciation_entries(schedule, nowdate())
			frappe.db.commit()  # nosemgrep: one asset's failure must not roll back the others
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=_("Depreciation posting failed for {0}").format(schedule))


def get_schedules_with_due_rows(date, company: str | None = None, asset: str | None = None) -> list[str]:
	ads = frappe.qb.DocType("Asset Depreciation Schedule")
	row = frappe.qb.DocType("Depreciation Schedule")
	query = (
		frappe.qb.from_(ads)
		.join(row)
		.on(row.parent == ads.name)
		.select(ads.name)
		.distinct()
		.where(
			(ads.docstatus == 1)
			& (row.schedule_date <= getdate(date))
			& ((row.journal_entry.isnull()) | (row.journal_entry == ""))
		)
	)
	if company:
		query = query.where(ads.company == company)
	if asset:
		query = query.where(ads.asset == asset)
	return query.run(pluck=True)


def make_depreciation_entries(schedule_name: str, date=None) -> list[str]:
	"""Post every unposted row of a schedule due on or before `date`, oldest first."""
	date = getdate(date or nowdate())
	schedule = frappe.get_doc("Asset Depreciation Schedule", schedule_name)
	if schedule.docstatus != 1:
		frappe.throw(
			_("Asset Depreciation Schedule {0} is not active").format(schedule_name), DepreciationError
		)

	# serialise postings per asset so concurrent runs cannot double-post a row
	frappe.db.get_value("Asset", schedule.asset, "name", for_update=True)
	asset = frappe.get_doc("Asset", schedule.asset)
	if asset.docstatus != 1:
		frappe.throw(_("Asset {0} is not submitted").format(asset.name), DepreciationError)

	posted = []
	for row in sorted(schedule.schedules, key=lambda r: r.idx):
		if row.journal_entry:
			continue
		if getdate(row.schedule_date) > date:
			break
		# re-read under the lock: another worker may have posted it meanwhile
		if frappe.db.get_value("Depreciation Schedule", row.name, "journal_entry"):
			continue
		posted.append(make_depreciation_entry(asset, schedule, row))
	return posted


def make_depreciation_entry(asset, schedule, row) -> str:
	cost_center = asset.cost_center or frappe.get_cached_value(
		"Company", asset.company, "default_cost_center"
	)
	remark = _("Depreciation of {0} ({1}) for {2}").format(
		asset.asset_name, asset.name, frappe.format(row.schedule_date, "Date")
	)
	je = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Depreciation Entry",
			"company": asset.company,
			"posting_date": row.schedule_date,
			"user_remark": remark,
			"title": _("Depreciation: {0}").format(asset.asset_name),
			"asset": asset.name,
			"asset_depreciation_schedule": schedule.name,
			"depreciation_schedule_row": row.name,
			"accounts": [
				{
					"account": asset.depreciation_expense_account,
					"cost_center": cost_center,
					"project": asset.get_project_on(row.schedule_date),
					"debit": row.depreciation_amount,
					"reference_type": "Asset",
					"reference_name": asset.name,
				},
				{
					"account": asset.accumulated_depreciation_account,
					"credit": row.depreciation_amount,
					"reference_type": "Asset",
					"reference_name": asset.name,
				},
			],
		}
	)
	je.flags.ignore_permissions = True
	je.insert()
	je.submit()
	return je.name


def on_depreciation_entry_submit(je):
	frappe.db.set_value("Depreciation Schedule", je.depreciation_schedule_row, "journal_entry", je.name)
	update_asset_values(je.asset)
	update_schedule_status(je.asset_depreciation_schedule)


def validate_depreciation_entry_cancel(je):
	"""Entries must be reversed newest first so book values stay sequential."""
	row_idx = frappe.db.get_value("Depreciation Schedule", je.depreciation_schedule_row, "idx")
	later = frappe.db.get_value(
		"Depreciation Schedule",
		{
			"parent": je.asset_depreciation_schedule,
			"idx": (">", row_idx),
			"journal_entry": ("is", "set"),
		},
		"journal_entry",
	)
	if later:
		frappe.throw(
			_("Cancel the later depreciation entry {0} first").format(frappe.bold(later)), DepreciationError
		)


def on_depreciation_entry_cancel(je):
	"""Free the schedule row so it can be posted again; the cancelled entry and its GL stay."""
	if frappe.db.get_value("Depreciation Schedule", je.depreciation_schedule_row, "journal_entry") == je.name:
		frappe.db.set_value("Depreciation Schedule", je.depreciation_schedule_row, "journal_entry", None)
	update_asset_values(je.asset)
	update_schedule_status(je.asset_depreciation_schedule)


def get_posted_depreciation(asset: str, to_date=None) -> float:
	"""Accumulated depreciation of an asset from the ledger (credits less reversals)."""
	account = frappe.db.get_value("Asset", asset, "accumulated_depreciation_account")
	if not account:
		return 0.0
	return -get_balance(account=account, reference_type="Asset", reference_name=asset, to_date=to_date)


def update_asset_values(asset_name: str):
	asset = frappe.get_doc("Asset", asset_name)
	accumulated = flt(get_posted_depreciation(asset_name), GL_PRECISION)
	values = {
		"accumulated_depreciation": accumulated,
		"value_after_depreciation": flt(asset.gross_purchase_amount - accumulated, GL_PRECISION),
	}
	if asset.docstatus == 1:
		values["status"] = get_asset_status(asset, accumulated)
	asset.db_set(values)


def get_asset_status(asset, accumulated: float) -> str:
	if not accumulated:
		return "Submitted"
	if flt(asset.gross_purchase_amount - accumulated, GL_PRECISION) <= flt(asset.salvage_value, GL_PRECISION):
		return "Fully Depreciated"
	return "Partially Depreciated"


def update_schedule_status(schedule_name: str):
	schedule = frappe.get_doc("Asset Depreciation Schedule", schedule_name)
	if schedule.docstatus != 1:
		return
	unposted = frappe.db.count(
		"Depreciation Schedule", {"parent": schedule_name, "journal_entry": ("is", "not set")}
	)
	schedule.db_set("status", "Active" if unposted else "Completed")


@frappe.whitelist()
def post_due_depreciation(
	asset: str | None = None, company: str | None = None, date: str | None = None
) -> list[str]:
	"""Manually post depreciation due on or before `date` for one asset or a whole company."""
	if asset:
		frappe.get_doc("Asset", asset).check_permission("submit")
	elif not frappe.has_permission("Journal Entry", "submit"):
		frappe.throw(_("Not permitted to post depreciation"), frappe.PermissionError)

	date = date or nowdate()
	posted = []
	for schedule in get_schedules_with_due_rows(date, company=company, asset=asset):
		posted += make_depreciation_entries(schedule, date)
	return posted
