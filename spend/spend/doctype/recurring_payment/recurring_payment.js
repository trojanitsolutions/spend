// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

const RP_METHOD = "spend.spend.doctype.recurring_payment.recurring_payment";

frappe.ui.form.on("Recurring Payment", {
	setup(frm) {
		const ledger = (extra) => () => ({ filters: { company: frm.doc.company, is_group: 0, disabled: 0, ...extra } });
		frm.set_query("expense_account", () => ({
			query: `${RP_METHOD}.get_recurring_accounts`,
			filters: { budget: frm.doc.budget, project: frm.doc.project },
		}));
		frm.set_query("budget", () => ({ filters: { company: frm.doc.company, docstatus: 1 } }));
		frm.set_query("paid_from", ledger({ account_type: ["in", ["Cash", "Bank"]] }));
		frm.set_query("cost_center", ledger({}));
		frm.set_query("project", () => ({ filters: { company: frm.doc.company, status: "Open" } }));
		frm.set_query("expense_category", () => ({ query: "spend.spend.doctype.expense_category.expense_category.get_categories", filters: { company: frm.doc.company, project: frm.doc.project } }));
		frm.set_query("expense_sub_category", () => ({
			query: "spend.spend.doctype.expense_category.expense_category.get_categories",
			filters: { company: frm.doc.company, project: frm.doc.project, parent_category: frm.doc.expense_category || "" },
		}));
	},

	expense_category(frm) {
		frm.set_value("expense_sub_category", "");
		frm.trigger("set_category_account");
	},

	expense_sub_category(frm) {
		frm.trigger("set_category_account");
	},

	// a category fills in its expense account
	set_category_account(frm) {
		if (!frm.doc.expense_category) return;
		frappe
			.call("spend.spend.expense_category.get_category_account", { category: frm.doc.expense_category, sub_category: frm.doc.expense_sub_category })
			.then(({ message }) => message && frm.set_value("expense_account", message));
	},

	refresh(frm) {
		frm.set_df_property("schedule", "read_only", frm.doc.frequency !== "Custom" || frm.doc.docstatus !== 0);
		if (frm.is_new()) return;
		frm.add_custom_button(__("Entries"), () => frappe.set_route("List", "Journal Entry", { recurring_payment: frm.doc.name }), __("View"));
		if (frm.doc.docstatus !== 1) return;

		const run = (method, message) =>
			frappe.call({ method: `${RP_METHOD}.${method}`, args: { name: frm.doc.name }, freeze: true }).then(({ message: result }) => {
				frappe.show_alert({ message: typeof message === "function" ? message(result) : message, indicator: "green" });
				frm.reload_doc();
			});
		if (frm.doc.status === "Active") {
			frm.add_custom_button(__("Post Due Now"), () =>
				run("post_due_payments", (posted) => (posted.length ? __("{0} payments posted", [posted.length]) : __("Nothing is due")))
			);
			frm.add_custom_button(__("Stop"), () => run("stop", __("Stopped")));
		}
		if (frm.doc.status === "Stopped") frm.add_custom_button(__("Resume"), () => run("resume", __("Resumed")));

		const pending = flt(frm.doc.total_amount) - flt(frm.doc.paid_amount);
		frm.dashboard.add_indicator(__("Paid {0} of {1}", [format_currency(frm.doc.paid_amount, frm.doc.currency), format_currency(frm.doc.total_amount, frm.doc.currency)]), pending > 0 ? "blue" : "green");
	},

	frequency(frm) {
		frm.set_df_property("schedule", "read_only", frm.doc.frequency !== "Custom");
		if (frm.doc.frequency !== "Custom") frm.clear_table("schedule"), frm.refresh_field("schedule");
	},

	project(frm) {
		if (!frm.doc.project) return;
		frappe.db.get_value("Project", frm.doc.project, ["budget", "cost_center"]).then(({ message }) => {
			if (message?.budget) frm.set_value("budget", message.budget);
			if (message?.cost_center && !frm.doc.cost_center) frm.set_value("cost_center", message.cost_center);
		});
	},
});
