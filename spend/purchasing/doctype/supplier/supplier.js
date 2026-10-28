// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Supplier", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Bills"), () => frappe.set_route("List", "Purchase Invoice", { supplier: frm.doc.name }), __("View"));
		frm.add_custom_button(__("Payments"), () => frappe.set_route("List", "Supplier Payment", { supplier: frm.doc.name }), __("View"));
		frm.add_custom_button(__("Supplier Outstanding"), () =>
			frappe.set_route("query-report", "Supplier Outstanding", { supplier: frm.doc.name }), __("View")
		);
		frappe
			.call("spend.purchasing.doctype.supplier.supplier.get_outstanding", { supplier: frm.doc.name })
			.then(({ message }) => {
				frm.dashboard.add_indicator(
					__("Outstanding: {0}", [format_currency(message || 0)]),
					message > 0 ? "orange" : "green"
				);
			});
	},
});
