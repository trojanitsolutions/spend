// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.query_reports["Budget vs Actual"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{ fieldname: "fiscal_year", label: __("Fiscal Year"), fieldtype: "Link", options: "Fiscal Year", reqd: 1 },
		{
			fieldname: "cost_center",
			label: __("Cost Center"),
			fieldtype: "Link",
			options: "Cost Center",
			get_query: () => ({ filters: { company: frappe.query_report.get_filter_value("company") } }),
		},
		{
			fieldname: "account",
			label: __("Account"),
			fieldtype: "Link",
			options: "Account",
			get_query: () => ({
				filters: { company: frappe.query_report.get_filter_value("company"), root_type: "Expense", is_group: 0 },
			}),
		},
		{ fieldname: "period", label: __("Period"), fieldtype: "Select", options: ["Yearly", "Monthly"], default: "Yearly" },
	],
	onload(report) {
		frappe.db
			.get_value("Fiscal Year", { start_date: ["<=", frappe.datetime.get_today()], end_date: [">=", frappe.datetime.get_today()], disabled: 0 }, "name")
			.then(({ message }) => message?.name && report.set_filter_value("fiscal_year", message.name));
	},
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "remaining" && data && data.remaining < 0) {
			value = `<span class="text-danger">${value}</span>`;
		}
		return value;
	},
};
