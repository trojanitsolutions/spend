import frappe

from spend.spend.setup import iter_standard_chart


def execute():
	"""Number the standard accounts of existing companies. Accounts that already have a number are kept."""
	for company in frappe.get_all("Company", pluck="name"):
		used = set(
			frappe.get_all(
				"Account",
				filters={"company": company, "account_number": ("is", "set")},
				pluck="account_number",
			)
		)
		for number, account_name in iter_standard_chart():
			if number in used:
				continue
			account = frappe.db.get_value(
				"Account",
				{"company": company, "account_name": account_name, "account_number": ("is", "not set")},
			)
			if account:
				frappe.db.set_value("Account", account, "account_number", number, update_modified=False)
				used.add(number)
