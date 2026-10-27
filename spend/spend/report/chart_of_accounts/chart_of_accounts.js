// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.query_reports["Chart of Accounts"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{ fieldname: "as_on_date", label: __("As On Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{
			fieldname: "root_type",
			label: __("Root Type"),
			fieldtype: "Select",
			options: ["", "Asset", "Liability", "Equity", "Income", "Expense"],
		},
		{ fieldname: "show_zero_balances", label: __("Show Zero Balances"), fieldtype: "Check", default: 1 },
		{ fieldname: "include_disabled", label: __("Include Disabled"), fieldtype: "Check" },
	],
	tree: true,
	name_field: "account",
	parent_field: "parent_account",
	initial_depth: 3,
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.is_group && column.fieldname === "account") value = `<b>${value}</b>`;
		return value;
	},
};
