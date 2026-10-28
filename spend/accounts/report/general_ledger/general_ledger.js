// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.query_reports["General Ledger"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.add_months(frappe.datetime.get_today(), -1) },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
		{ fieldname: "account", label: __("Account"), fieldtype: "Link", options: "Account" },
		{ fieldname: "cost_center", label: __("Cost Center"), fieldtype: "Link", options: "Cost Center" },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "party", label: __("Supplier"), fieldtype: "Link", options: "Supplier" },
		{ fieldname: "voucher_no", label: __("Voucher No"), fieldtype: "Data" },
		{ fieldname: "group_by_account", label: __("Group by Account"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		return data && data.bold ? value.bold() : value;
	},
};
