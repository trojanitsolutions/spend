// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Frontend Template", {
	refresh(frm) {
		if (!frm.is_new()) frm.add_custom_button(__("Open Spend"), () => window.open("/spend"));
	},
});
