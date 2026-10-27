// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.treeview_settings["Account"] = {
	title: __("Chart of Accounts"),
	breadcrumb: "Spend",
	get_tree_root: false,
	root_label: "All Accounts",
	get_tree_nodes: "spend.spend.doctype.account.account.get_children",
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
		{ fieldtype: "Data", fieldname: "account_name", label: __("Account Name"), reqd: 1 },
		{ fieldtype: "Data", fieldname: "account_number", label: __("Account Number") },
		{ fieldtype: "Check", fieldname: "is_group", label: __("Is Group") },
		{
			fieldtype: "Select",
			fieldname: "account_type",
			label: __("Account Type"),
			options: frappe.meta.get_docfield("Account", "account_type")?.options,
		},
	],
	ignore_fields: ["parent_account"],
	get_label(node) {
		const number = node.data?.account_number;
		const title = node.title || node.label;
		return frappe.utils.escape_html(number ? `${number} · ${title}` : title);
	},
	onrender(node) {
		if (node.is_root || !node.data || node.data.balance === undefined) return;
		const currency = node.data.account_currency;
		const balance = node.data.balance;
		const tone = balance < 0 ? "text-warning" : "text-muted";
		$(node.parent)
			.find("> .tree-label, > .tree-link")
			.first()
			.append(`<span class="ml-3 small ${tone}">${format_currency(balance, currency)}</span>`);
	},
	onload(treeview) {
		frappe.treeview_settings["Account"].treeview = treeview;
		treeview.page.add_inner_button(__("Cost Centers"), () =>
			frappe.set_route("Tree", "Cost Center", { company: treeview.page.fields_dict.company.get_value() })
		);
		treeview.page.add_inner_button(__("Chart of Accounts Report"), () =>
			frappe.set_route("query-report", "Chart of Accounts", { company: treeview.page.fields_dict.company.get_value() })
		);
	},
	toolbar: [
		{
			label: __("Ledger"),
			condition: (node) => !node.is_root && !node.expandable,
			click: (node) => frappe.set_route("List", "GL Entry", { account: node.label, is_cancelled: 0 }),
		},
	],
	extend_toolbar: true,
};
