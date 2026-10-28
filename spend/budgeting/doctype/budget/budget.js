// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Budget", {
	setup(frm) {
		frm.set_query("cost_center", () => ({ filters: { company: frm.doc.company, disabled: 0 } }));
		frm.set_query("account", "accounts", () => ({
			filters: { company: frm.doc.company, is_group: 0, disabled: 0, root_type: "Expense" },
		}));
	},

	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;
		frm.add_custom_button(__("Budget vs Actual"), () =>
			frappe.set_route("query-report", "Budget vs Actual", {
				company: frm.doc.company,
				fiscal_year: frm.doc.fiscal_year,
				cost_center: frm.doc.cost_center,
				period: frm.doc.budget_period === "Monthly" ? "Monthly" : "Yearly",
			})
		);
		frappe.call("spend.budgeting.doctype.budget.budget.get_budget_summary", { budget: frm.doc.name }).then(({ message }) => {
			if (!message) return;
			const fmt = (v) => format_currency(v, message.currency);
			const tone = message.utilization > 100 ? "red" : message.utilization >= 80 ? "orange" : "green";
			frm.dashboard.add_indicator(__("Allocated {0}", [fmt(message.allocated)]), "blue");
			frm.dashboard.add_indicator(__("Spent {0}", [fmt(message.actual)]), tone);
			frm.dashboard.add_indicator(__("Remaining {0}", [fmt(message.remaining)]), message.remaining < 0 ? "red" : "gray");
			frm.dashboard.add_indicator(__("{0}% used", [message.utilization]), tone);
			frm.dashboard.add_progress(
				__("Budget Utilization"),
				Math.min(message.utilization, 100),
				__("{0} of {1} spent", [fmt(message.actual), fmt(message.allocated)])
			);
		});
	},

	budget_period(frm) {
		if (frm.doc.budget_period !== "Monthly") frm.clear_table("monthly_distribution");
		frm.refresh_field("monthly_distribution");
	},

	fiscal_year(frm) {
		frm.clear_table("monthly_distribution");
		frm.refresh_field("monthly_distribution");
	},
});
