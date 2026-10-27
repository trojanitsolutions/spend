// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.query_reports["Project Category Monthly"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
			get_query: () => ({ filters: { company: frappe.query_report.get_filter_value("company") } }),
		},
		{
			fieldname: "expense_category",
			label: __("Category"),
			fieldtype: "Link",
			options: "Expense Category",
			get_query: () => ({ filters: { company: frappe.query_report.get_filter_value("company"), is_parent_category: 1 } }),
		},
		{ fieldname: "fiscal_year", label: __("Fiscal Year"), fieldtype: "Link", options: "Fiscal Year" },
	],
	tree: true,
	name_field: "category",
	parent_field: "parent_category",
	initial_depth: 1,
};
