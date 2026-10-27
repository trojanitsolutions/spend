# Copyright (c) 2026, Trojan IT Solutions and Contributors
# See license.txt

"""Pure depreciation maths. No database records needed."""

from frappe.tests import UnitTestCase
from frappe.utils import getdate

from spend.spend.depreciation import (
	DepreciationError,
	calculate_schedule,
	get_default_start_date,
	get_number_of_depreciations,
	get_schedule_dates,
)


def schedule(cost, salvage, method, frequency, years, start="2025-01-31", rate=None):
	n = get_number_of_depreciations(years, frequency)
	return calculate_schedule(cost, salvage, method, frequency, n, start, annual_rate=rate)


class UnitTestDepreciationMaths(UnitTestCase):
	def assert_consistent(self, rows, cost, salvage):
		opening = cost
		accumulated = 0
		for row in rows:
			self.assertEqual(row["opening_book_value"], opening)
			self.assertAlmostEqual(row["closing_book_value"], opening - row["depreciation_amount"], places=2)
			accumulated += row["depreciation_amount"]
			self.assertAlmostEqual(row["accumulated_depreciation_amount"], accumulated, places=2)
			self.assertGreaterEqual(row["closing_book_value"], salvage)
			opening = row["closing_book_value"]
		self.assertAlmostEqual(rows[-1]["closing_book_value"], salvage, places=2)

	def test_number_of_depreciations(self):
		self.assertEqual(get_number_of_depreciations(5, "Monthly"), 60)
		self.assertEqual(get_number_of_depreciations(5, "Quarterly"), 20)
		self.assertEqual(get_number_of_depreciations(5, "Half-Yearly"), 10)
		self.assertEqual(get_number_of_depreciations(5, "Yearly"), 5)
		self.assertEqual(get_number_of_depreciations(2.5, "Half-Yearly"), 5)
		self.assertRaises(DepreciationError, get_number_of_depreciations, 2.5, "Yearly")
		self.assertRaises(DepreciationError, get_number_of_depreciations, 0, "Monthly")

	def test_straight_line_monthly(self):
		rows = schedule(120000, 0, "Straight Line", "Monthly", 1)
		self.assertEqual(len(rows), 12)
		self.assertTrue(all(r["depreciation_amount"] == 10000 for r in rows))
		self.assert_consistent(rows, 120000, 0)

	def test_straight_line_with_salvage_and_rounding(self):
		rows = schedule(1000, 100, "Straight Line", "Yearly", 7)
		self.assertEqual([r["depreciation_amount"] for r in rows[:6]], [128.57] * 6)
		self.assertEqual(rows[-1]["depreciation_amount"], 128.58)  # last period absorbs rounding
		self.assert_consistent(rows, 1000, 100)

	def test_straight_line_frequencies(self):
		for frequency, count, amount in (
			("Quarterly", 12, 2500),
			("Half-Yearly", 6, 5000),
			("Yearly", 3, 10000),
		):
			rows = schedule(40000, 10000, "Straight Line", frequency, 3)
			self.assertEqual(len(rows), count)
			self.assertEqual(rows[0]["depreciation_amount"], amount)
			self.assert_consistent(rows, 40000, 10000)

	def test_wdv_with_rate(self):
		rows = schedule(100000, 10000, "Written Down Value", "Yearly", 5, rate=40)
		self.assertEqual([r["depreciation_amount"] for r in rows], [40000, 24000, 14400, 8640, 2960])
		self.assert_consistent(rows, 100000, 10000)

	def test_wdv_derived_rate_reaches_salvage(self):
		rows = schedule(500000, 25000, "Written Down Value", "Quarterly", 4)
		self.assertEqual(len(rows), 16)
		amounts = [r["depreciation_amount"] for r in rows]
		self.assertEqual(amounts, sorted(amounts, reverse=True))
		self.assert_consistent(rows, 500000, 25000)

	def test_wdv_monthly_rate_is_compound_equivalent(self):
		yearly = schedule(100000, 1000, "Written Down Value", "Yearly", 2, rate=30)
		monthly = schedule(100000, 1000, "Written Down Value", "Monthly", 2, rate=30)
		self.assertAlmostEqual(monthly[11]["closing_book_value"], yearly[0]["closing_book_value"], delta=1)

	def test_never_below_salvage(self):
		rows = schedule(1000, 500, "Written Down Value", "Yearly", 3, rate=90)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["depreciation_amount"], 500)
		self.assertEqual(rows[0]["closing_book_value"], 500)

	def test_wdv_needs_rate_or_salvage(self):
		self.assertRaises(DepreciationError, schedule, 1000, 0, "Written Down Value", "Yearly", 3)

	def test_invalid_salvage(self):
		self.assertRaises(DepreciationError, schedule, 1000, 1000, "Straight Line", "Yearly", 3)
		self.assertRaises(DepreciationError, schedule, 1000, -1, "Straight Line", "Yearly", 3)

	def test_month_end_dates_stay_month_end(self):
		dates = get_schedule_dates("2025-01-31", 4, "Monthly")
		self.assertEqual(
			dates, [getdate(d) for d in ("2025-01-31", "2025-02-28", "2025-03-31", "2025-04-30")]
		)
		self.assertEqual(
			get_schedule_dates("2025-03-15", 3, "Quarterly"),
			[getdate(d) for d in ("2025-03-15", "2025-06-15", "2025-09-15")],
		)

	def test_default_start_date(self):
		self.assertEqual(get_default_start_date("2025-01-10", "Monthly"), getdate("2025-01-31"))
		self.assertEqual(get_default_start_date("2025-01-10", "Quarterly"), getdate("2025-03-31"))
		self.assertEqual(get_default_start_date("2025-01-10", "Yearly"), getdate("2025-12-31"))
