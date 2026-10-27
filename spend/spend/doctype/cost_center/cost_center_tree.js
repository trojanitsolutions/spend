// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.treeview_settings["Cost Center"] = {
	title: __("Cost Centers"),
	breadcrumb: "Spend",
	get_tree_root: false,
	root_label: "All Cost Centers",
	get_tree_nodes: "spend.spend.doctype.cost_center.cost_center.get_children",
	filters: [
		{
			fieldname: "company",
			fieldtype: "Link",
			options: "Company",
			label: __("Company"),
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
	],
	fields: [
		{ fieldtype: "Data", fieldname: "cost_center_name", label: __("Cost Center Name"), reqd: 1 },
		{ fieldtype: "Check", fieldname: "is_group", label: __("Is Group") },
	],
	ignore_fields: ["parent_cost_center"],
	onload(treeview) {
		treeview.page.add_inner_button(__("Spending Report"), () =>
			frappe.set_route("query-report", "Cost Center-wise Spending", { company: treeview.page.fields_dict.company.get_value() })
		);
	},
};
