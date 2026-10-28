// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Item Group", {
	setup(frm) {
		frm.set_query("parent_item_group", () => ({ filters: { is_group: 1, name: ["!=", frm.doc.name] } }));
		const of_company = (doc, cdt, cdn) => ({ filters: { company: locals[cdt][cdn].company, is_group: 0, disabled: 0 } });
		frm.set_query("expense_account", "item_group_defaults", (doc, cdt, cdn) => {
			const query = of_company(doc, cdt, cdn);
			query.filters.root_type = "Expense";
			return query;
		});
		frm.set_query("buying_cost_center", "item_group_defaults", of_company);
	},
});
