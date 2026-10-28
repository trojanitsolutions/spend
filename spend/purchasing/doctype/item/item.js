// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Item", {
	setup(frm) {
		frm.set_query("item_group", () => ({ filters: {} }));
		const enabled = () => ({ filters: { enabled: 1 } });
		frm.set_query("stock_uom", enabled);
		frm.set_query("purchase_uom", enabled);
		frm.set_query("uom", "uoms", enabled);
	},
});
