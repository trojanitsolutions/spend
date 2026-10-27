// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Cost Center", {
	setup(frm) {
		frm.set_query("parent_cost_center", () => ({ filters: { company: frm.doc.company, is_group: 1 } }));
	},

	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Spending Report"), () =>
			frappe.set_route("query-report", "Cost Center-wise Spending", { company: frm.doc.company })
		);
		frm.add_custom_button(__("Budgets"), () => frappe.set_route("List", "Budget", { cost_center: frm.doc.name }));
	},
});
