// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.query_reports["Budget Utilization"] = {
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
	],
	onload(report) {
		frappe.db
			.get_value("Fiscal Year", { start_date: ["<=", frappe.datetime.get_today()], end_date: [">=", frappe.datetime.get_today()], disabled: 0 }, "name")
			.then(({ message }) => message?.name && report.set_filter_value("fiscal_year", message.name));
	},
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "utilization_status" && data) {
			const color = { "On Track": "green", "Near Limit": "orange", Exceeded: "red" }[data.utilization_status];
			value = `<span class="indicator-pill ${color}">${value}</span>`;
		}
		return value;
	},
};
