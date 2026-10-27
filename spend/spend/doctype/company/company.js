// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

const COMPANY_ACCOUNT_ROOTS = {
	default_cash_account: ["Asset"],
	default_payable_account: ["Liability"],
	default_expense_account: ["Expense"],
	fixed_asset_account: ["Asset"],
	accumulated_depreciation_account: ["Asset"],
	depreciation_expense_account: ["Expense"],
};

frappe.ui.form.on("Company", {
	setup(frm) {
		for (const [fieldname, root_types] of Object.entries(COMPANY_ACCOUNT_ROOTS)) {
			frm.set_query(fieldname, () => ({
				filters: { company: frm.doc.name, is_group: 0, disabled: 0, root_type: ["in", root_types] },
			}));
		}
		frm.set_query("default_cost_center", () => ({ filters: { company: frm.doc.name, is_group: 0 } }));
	},

	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Chart of Accounts"), () => frappe.set_route("Tree", "Account", { company: frm.doc.name }), __("View"));
		frm.add_custom_button(__("Cost Centers"), () => frappe.set_route("Tree", "Cost Center", { company: frm.doc.name }), __("View"));
		frm.add_custom_button(__("Asset Register"), () => frappe.set_route("query-report", "Asset Register", { company: frm.doc.name }), __("View"));
	},

	company_name(frm) {
		if (frm.is_new() && !frm.doc.abbr && frm.doc.company_name) {
			const words = frm.doc.company_name.trim().split(/\s+/);
			const abbr = words.length > 1 ? words.map((w) => w[0]).join("") : words[0].slice(0, 4);
			frm.set_value("abbr", abbr.toUpperCase());
		}
	},
});
