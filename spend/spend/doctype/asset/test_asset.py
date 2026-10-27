# Copyright (c) 2026, Trojan IT Solutions and Contributors
# See license.txt

import frappe

from spend.spend.accounting import get_balance
from spend.spend.depreciation import post_due_depreciation
from spend.spend.doctype.asset_depreciation_schedule.asset_depreciation_schedule import DuplicateScheduleError
from spend.spend.doctype.journal_entry.journal_entry import DuplicateDepreciationError
from spend.tests.utils import SpendTestCase, account, make_asset, make_company, setup_test_data

IGNORE_TEST_RECORD_DEPENDENCIES = [
	"Company",
	"Account",
	"Cost Center",
	"Journal Entry",
	"Asset Depreciation Schedule",
]


def schedule_rows(asset):
	return frappe.get_doc("Asset Depreciation Schedule", asset.depreciation_schedule).schedules


class IntegrationTestAsset(SpendTestCase):
	def test_submit_generates_schedule_and_capitalization(self):
		asset = make_asset()
		asset.reload()
		ads = frappe.get_doc("Asset Depreciation Schedule", asset.depreciation_schedule)
		self.assertEqual(ads.docstatus, 1)
		self.assertEqual(ads.status, "Active")
		self.assertEqual(len(ads.schedules), 12)
		self.assertEqual(ads.total_depreciation, 120000)
		self.assertEqual(asset.status, "Submitted")
		self.assertEqual(asset.value_after_depreciation, 120000)
		self.assertEqual(
			get_balance(
				account=account("Office Equipment"), reference_type="Asset", reference_name=asset.name
			),
			120000,
		)

	def test_draft_save_keeps_a_single_schedule(self):
		asset = make_asset(submit=False)
		asset.useful_life_years = 2
		asset.save()
		schedules = frappe.get_all("Asset Depreciation Schedule", filters={"asset": asset.name})
		self.assertEqual(len(schedules), 1)
		self.assertEqual(len(schedule_rows(asset)), 24)

	def test_second_schedule_rejected(self):
		asset = make_asset()
		duplicate = frappe.new_doc("Asset Depreciation Schedule")
		duplicate.set_from_asset(asset)
		self.assertRaises(DuplicateScheduleError, duplicate.insert, ignore_permissions=True)

	def test_post_due_depreciation(self):
		asset = make_asset()
		posted = post_due_depreciation(asset=asset.name, date="2025-03-31")
		self.assertEqual(len(posted), 3)  # Jan, Feb, Mar month-ends

		rows = schedule_rows(asset)
		self.assertEqual([bool(r.journal_entry) for r in rows[:4]], [True, True, True, False])
		je = frappe.get_doc("Journal Entry", rows[0].journal_entry)
		self.assertEqual(je.voucher_type, "Depreciation Entry")
		self.assertEqual(je.depreciation_schedule_row, rows[0].name)
		debit = next(r for r in je.accounts if r.debit)
		credit = next(r for r in je.accounts if r.credit)
		self.assertEqual((debit.account, debit.debit), (account("Depreciation"), 10000))
		self.assertEqual((credit.account, credit.credit), (account("Accumulated Depreciation"), 10000))

		asset.reload()
		self.assertEqual(asset.accumulated_depreciation, 30000)
		self.assertEqual(asset.value_after_depreciation, 90000)
		self.assertEqual(asset.status, "Partially Depreciated")
		self.assertEqual(get_balance(account=account("Depreciation")), 30000)

	def test_no_duplicate_postings(self):
		asset = make_asset()
		post_due_depreciation(asset=asset.name, date="2025-01-31")
		self.assertEqual(post_due_depreciation(asset=asset.name, date="2025-01-31"), [])

		row = schedule_rows(asset)[0]
		je = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"voucher_type": "Depreciation Entry",
				"company": asset.company,
				"posting_date": row.schedule_date,
				"asset": asset.name,
				"asset_depreciation_schedule": asset.depreciation_schedule,
				"depreciation_schedule_row": row.name,
				"accounts": [
					{"account": account("Depreciation"), "debit": 10000},
					{"account": account("Accumulated Depreciation"), "credit": 10000},
				],
			}
		)
		self.assertRaises(DuplicateDepreciationError, je.insert)
		self.assertEqual(
			frappe.db.count("Journal Entry", {"asset": asset.name, "voucher_type": "Depreciation Entry"}), 1
		)

	def test_cancel_reverses_and_allows_repost(self):
		asset = make_asset()
		first, second = post_due_depreciation(asset=asset.name, date="2025-02-28")

		# newest first
		self.assertRaises(frappe.ValidationError, frappe.get_doc("Journal Entry", first).cancel)
		frappe.get_doc("Journal Entry", second).cancel()

		gl = frappe.get_all("GL Entry", filters={"voucher_no": second}, fields=["is_cancelled"])
		self.assertEqual(len(gl), 4)  # 2 originals + 2 reversals, nothing deleted
		self.assertTrue(all(g.is_cancelled for g in gl))
		self.assertEqual(frappe.db.get_value("Journal Entry", second, "docstatus"), 2)
		self.assertFalse(schedule_rows(asset)[1].journal_entry)
		self.assertEqual(asset.reload().accumulated_depreciation, 10000)

		reposted = post_due_depreciation(asset=asset.name, date="2025-02-28")
		self.assertEqual(len(reposted), 1)
		self.assertNotEqual(reposted[0], second)
		self.assertEqual(asset.reload().accumulated_depreciation, 20000)

	def test_fully_depreciated(self):
		asset = make_asset(
			salvage_value=6000, gross_purchase_amount=126000, frequency_of_depreciation="Quarterly"
		)
		post_due_depreciation(asset=asset.name, date="2026-12-31")
		asset.reload()
		self.assertEqual(asset.status, "Fully Depreciated")
		self.assertEqual(asset.value_after_depreciation, 6000)  # never below salvage
		self.assertEqual(
			frappe.db.get_value("Asset Depreciation Schedule", asset.depreciation_schedule, "status"),
			"Completed",
		)

	def test_asset_cancel(self):
		asset = make_asset()
		post_due_depreciation(asset=asset.name, date="2025-01-31")
		self.assertRaises(frappe.ValidationError, asset.cancel)

		je = schedule_rows(asset)[0].journal_entry
		frappe.get_doc("Journal Entry", je).cancel()
		asset.reload().cancel()

		self.assertEqual(asset.reload().status, "Cancelled")
		self.assertEqual(
			frappe.db.get_value("Asset Depreciation Schedule", asset.depreciation_schedule, "docstatus"), 2
		)
		self.assertEqual(frappe.db.get_value("Journal Entry", asset.capitalization_entry, "docstatus"), 2)
		self.assertEqual(get_balance(account=account("Office Equipment")), 0)
		self.assertTrue(frappe.db.exists("GL Entry", {"voucher_no": asset.capitalization_entry}))

	def test_capitalization_entry_cannot_be_cancelled_alone(self):
		asset = make_asset()
		self.assertRaises(
			frappe.ValidationError, frappe.get_doc("Journal Entry", asset.capitalization_entry).cancel
		)

	def test_validations(self):
		self.assertRaises(frappe.ValidationError, make_asset, salvage_value=120000)
		self.assertRaises(frappe.ValidationError, make_asset, depreciation_start_date="2024-12-31")
		self.assertRaises(frappe.ValidationError, make_asset, available_for_use_date="2024-12-01")
		self.assertRaises(
			frappe.ValidationError, make_asset, useful_life_years=1.1, frequency_of_depreciation="Quarterly"
		)
		make_company("_Test Spend Company 2", "_TS2")
		self.assertRaises(frappe.ValidationError, make_asset, fixed_asset_account="Office Equipment - _TS2")
		self.assertRaises(
			frappe.ValidationError, make_asset, depreciation_expense_account=account("Creditors")
		)

	def test_written_down_value_asset(self):
		asset = make_asset(
			depreciation_method="Written Down Value",
			frequency_of_depreciation="Yearly",
			useful_life_years=5,
			gross_purchase_amount=100000,
			salvage_value=10000,
			rate_of_depreciation=40,
		)
		amounts = [r.depreciation_amount for r in schedule_rows(asset)]
		self.assertEqual(amounts, [40000, 24000, 14400, 8640, 2960])
