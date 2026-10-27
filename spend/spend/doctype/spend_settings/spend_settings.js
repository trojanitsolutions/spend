// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Spend Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Approval Workflows"), () => frappe.set_route("List", "Workflow"));
	},
});
