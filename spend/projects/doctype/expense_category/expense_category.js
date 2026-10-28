// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Expense Category", {
	setup(frm) {
		frm.set_query("parent_category", () => ({
			filters: { company: frm.doc.company, is_parent_category: 1, disabled: 0, name: ["!=", frm.doc.name || ""] },
		}));
		frm.set_query("expense_account", () => ({ filters: { company: frm.doc.company, is_group: 0, root_type: "Expense" } }));
	},

	refresh(frm) {
		if (frm.is_new() || !frm.doc.is_parent_category) return;
		frm.add_custom_button(__("Sub Categories"), () => frappe.set_route("List", "Expense Category", { parent_category: frm.doc.name }));
	},
});
