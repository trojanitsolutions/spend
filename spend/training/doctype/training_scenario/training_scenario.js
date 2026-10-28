// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Training Scenario", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Edit in Spend"), () =>
			window.open(`/spend/training/${encodeURIComponent(frm.doc.name)}/edit`)
		);
	},
});
