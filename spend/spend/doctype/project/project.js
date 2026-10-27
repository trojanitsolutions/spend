// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Project", {
	setup(frm) {
		frm.set_query("budget", () => ({ filters: { company: frm.doc.company, docstatus: 1 } }));
		frm.set_query("cost_center", () => ({ filters: { company: frm.doc.company, is_group: 0, disabled: 0 } }));
		frm.set_query("account", "budget_accounts", () => ({
			query: "spend.spend.doctype.project.project.get_budget_accounts",
			filters: { budget: frm.doc.budget || "" },
		}));
		frm.set_query("expense_category", "expense_categories", () => ({ query: "spend.spend.doctype.expense_category.expense_category.get_categories", filters: { company: frm.doc.company } }));
		frm.set_query("expense_sub_category", "expense_categories", (doc, cdt, cdn) => ({
			query: "spend.spend.doctype.expense_category.expense_category.get_categories",
			filters: { company: doc.company, parent_category: locals[cdt][cdn].expense_category || "" },
		}));
	},

	budget(frm) {
		if (!frm.doc.budget) return;
		frappe.db.get_value("Budget", frm.doc.budget, ["cost_center", "action_if_exceeded"]).then(({ message }) => {
			frappe.db.get_value("Cost Center", message.cost_center, "is_group").then((r) => {
				if (!r.message.is_group) frm.set_value("cost_center", message.cost_center);
			});
			frm.set_value("action_if_exceeded", message.action_if_exceeded);
		});
	},

	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Bills"), () => frappe.set_route("List", "Purchase Invoice", { project: frm.doc.name }), __("View"));
		frm.add_custom_button(__("Payments"), () => frappe.set_route("List", "Supplier Payment", { project: frm.doc.name }), __("View"));
		frm.add_custom_button(__("Ledger"), () => frappe.set_route("List", "GL Entry", { project: frm.doc.name }), __("View"));
		frm.add_custom_button(__("Project Spend"), () =>
			frappe.set_route("query-report", "Project Spend", { company: frm.doc.company, project: frm.doc.name }), __("View")
		);
		frappe.call("spend.spend.doctype.project.project.get_project_summary", { project: frm.doc.name }).then(({ message }) => {
			const budget = flt(frm.doc.budget_amount);
			const over = budget && message.spent > budget;
			frm.dashboard.add_indicator(
				budget
					? __("Spent {0} of {1}", [format_currency(message.spent, frm.doc.currency), format_currency(budget, frm.doc.currency)])
					: __("Spent {0}", [format_currency(message.spent, frm.doc.currency)]),
				over ? "red" : message.utilization >= 80 ? "orange" : "green"
			);
			if (message.outstanding > 0) {
				frm.dashboard.add_indicator(__("Owed to suppliers: {0}", [format_currency(message.outstanding, frm.doc.currency)]), "orange");
			}
		});
	},
});
