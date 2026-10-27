frappe.treeview_settings["Item Group"] = {
	breadcrumb: "Spend",
	title: __("Item Group"),
	get_tree_root: false,
	root_label: "All Item Groups",
	get_tree_nodes: "frappe.desk.treeview.get_children",
	add_tree_node: "frappe.desk.treeview.add_node",
	ignore_fields: ["parent_item_group"],
};
