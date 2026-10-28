frappe.treeview_settings["Task"] = {
	get_tree_nodes: "spend.projects.doctype.task.task.get_children",
	add_tree_node: "spend.projects.doctype.task.task.add_node",
	filters: [{ fieldname: "project", fieldtype: "Link", options: "Project", label: __("Project"), reqd: 1 }],
	breadcrumb: "Projects",
	get_tree_root: false,
	root_label: "All Tasks",
	ignore_fields: ["parent_task"],
	onload(me) {
		frappe.treeview_settings["Task"].page = me.page;
	},
};
