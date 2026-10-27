// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Account", {
	setup(frm) {
		frm.set_query("parent_account", () => ({ filters: { company: frm.doc.company, is_group: 1 } }));
	},

	refresh(frm) {
		frm.toggle_enable("root_type", !frm.doc.parent_account);
		if (frm.is_new()) return;

		frm.add_custom_button(__("Ledger"), () =>
			frappe.set_route("List", "GL Entry", { account: frm.doc.name, is_cancelled: 0 })
		);
		frm.add_custom_button(__("Chart of Accounts"), () =>
			frappe.set_route("Tree", "Account", { company: frm.doc.company })
		);
		frappe
			.call("spend.spend.doctype.account.account.get_account_balance", { account: frm.doc.name })
			.then(({ message }) => {
				const currency = frm.doc.account_currency;
				frm.dashboard.add_indicator(
					__("Balance: {0}", [format_currency(message, currency)]),
					message === 0 ? "gray" : message > 0 ? "blue" : "orange"
				);
			});
	},

	parent_account(frm) {
		frm.toggle_enable("root_type", !frm.doc.parent_account);
	},
});
