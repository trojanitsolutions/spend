// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Journal Entry", {
	setup(frm) {
		frm.set_query("account", "accounts", () => ({
			filters: { company: frm.doc.company, is_group: 0, disabled: 0 },
		}));
		frm.set_query("cost_center", "accounts", () => ({
			filters: { company: frm.doc.company, is_group: 0, disabled: 0 },
		}));
		frm.set_query("project", "accounts", () => ({
			filters: { company: frm.doc.company, status: "Open" },
		}));
		const category = (parent) => (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			return { query: "spend.spend.doctype.expense_category.expense_category.get_categories", filters: { company: doc.company, project: row.project, ...(parent ? { parent_category: row.expense_category || "" } : {}) } };
		};
		frm.set_query("expense_category", "accounts", category(false));
		frm.set_query("expense_sub_category", "accounts", category(true));
		frm.ignore_doctypes_on_cancel_all = ["GL Entry", "Asset", "Asset Depreciation Schedule"];
	},

	refresh(frm) {
		const system_entry = ["Depreciation Entry", "Asset Capitalization"].includes(frm.doc.voucher_type) && frm.doc.asset;
		frm.set_df_property("voucher_type", "read_only", system_entry ? 1 : 0);
		if (frm.doc.docstatus > 0) {
			frm.add_custom_button(__("Ledger"), () => frappe.set_route("List", "GL Entry", { voucher_no: frm.doc.name }));
		}
		frm.trigger("set_difference");
	},

	set_difference(frm) {
		let debit = 0;
		let credit = 0;
		(frm.doc.accounts || []).forEach((row) => {
			debit += flt(row.debit);
			credit += flt(row.credit);
		});
		frm.set_value("total_debit", debit);
		frm.set_value("total_credit", credit);
		if (frm.doc.docstatus === 0 && Math.abs(debit - credit) >= 0.01) {
			frm.dashboard.set_headline(
				__("Difference: {0}", [format_currency(debit - credit, frm.doc.currency)]),
				"orange"
			);
		} else {
			frm.dashboard.clear_headline();
		}
	},
});

frappe.ui.form.on("Journal Entry Account", {
	debit(frm, cdt, cdn) {
		if (flt(locals[cdt][cdn].debit)) frappe.model.set_value(cdt, cdn, "credit", 0);
		frm.trigger("set_difference");
	},
	credit(frm, cdt, cdn) {
		if (flt(locals[cdt][cdn].credit)) frappe.model.set_value(cdt, cdn, "debit", 0);
		frm.trigger("set_difference");
	},
	accounts_remove(frm) {
		frm.trigger("set_difference");
	},
	accounts_add(frm, cdt, cdn) {
		// pre-fill the balancing amount on a new row
		let diff = 0;
		frm.doc.accounts.forEach((row) => (diff += flt(row.debit) - flt(row.credit)));
		if (diff > 0) frappe.model.set_value(cdt, cdn, "credit", diff);
		else if (diff < 0) frappe.model.set_value(cdt, cdn, "debit", -diff);
	},
});

// a category fills in its expense account
frappe.ui.form.on("Journal Entry Account", {
	expense_category(frm, cdt, cdn) {
		frappe.model.set_value(cdt, cdn, "expense_sub_category", "");
		set_category_account(cdt, cdn, "account");
	},
	expense_sub_category(frm, cdt, cdn) {
		set_category_account(cdt, cdn, "account");
	},
});

function set_category_account(cdt, cdn, fieldname) {
	const row = locals[cdt][cdn];
	if (!row.expense_category && !row.expense_sub_category) return;
	frappe
		.call("spend.spend.expense_category.get_category_account", { category: row.expense_category, sub_category: row.expense_sub_category })
		.then(({ message }) => message && frappe.model.set_value(cdt, cdn, fieldname, message));
}
