// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Purchase Invoice", {
	setup(frm) {
		const ledger = (extra = {}) => () => ({ filters: { company: frm.doc.company, is_group: 0, disabled: 0, ...extra } });
		frm.set_query("credit_to", ledger({ account_type: "Payable" }));
		frm.set_query("expense_account", "items", ledger({ root_type: "Expense" }));
		frm.set_query("cost_center", ledger());
		frm.set_query("cost_center", "items", ledger());
		frm.set_query("supplier", () => ({ filters: { disabled: 0 } }));
		frm.set_query("item_code", "items", () => ({ filters: { disabled: 0 } }));
		frm.set_query("uom", "items", (doc, cdt, cdn) => ({
			query: "spend.spend.doctype.item.item.get_item_uoms",
			filters: { item_code: locals[cdt][cdn].item_code || "" },
		}));
		const open_project = () => ({ filters: { company: frm.doc.company, status: "Open" } });
		frm.set_query("project", open_project);
		frm.set_query("project", "items", open_project);
		const category = (parent) => (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			return {
				query: "spend.spend.doctype.expense_category.expense_category.get_categories",
				filters: { company: doc.company, project: row.project || doc.project, ...(parent ? { parent_category: row.expense_category || "" } : {}) },
			};
		};
		frm.set_query("expense_category", "items", category(false));
		frm.set_query("expense_sub_category", "items", category(true));
		frm.ignore_doctypes_on_cancel_all = ["GL Entry", "Supplier Payment"];
	},

	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Ledger"), () => frappe.set_route("List", "GL Entry", { voucher_no: frm.doc.name }));
			if (flt(frm.doc.outstanding_amount) > 0) {
				frm.add_custom_button(__("Make Payment"), () =>
					frappe.model.open_mapped_doc({
						method: "spend.spend.doctype.purchase_invoice.purchase_invoice.make_supplier_payment",
						frm,
					})
				);
			}
		}
	},

	company(frm) {
		if (!frm.doc.company) return;
		frappe.db
			.get_value("Company", frm.doc.company, ["default_payable_account", "default_cost_center"])
			.then(({ message }) => {
				frm.set_value("credit_to", message.default_payable_account);
				frm.set_value("cost_center", message.default_cost_center);
			});
	},

	project(frm) {
		(frm.doc.items || []).forEach((item) => {
			if (!item.project) item.project = frm.doc.project;
		});
		frm.refresh_field("items");
		if (frm.doc.project && !frm.doc.cost_center) {
			frappe.db.get_value("Project", frm.doc.project, "cost_center").then(({ message }) => {
				if (message.cost_center) frm.set_value("cost_center", message.cost_center);
			});
		}
	},

	posting_date(frm) {
		if (!frm.doc.due_date && frm.doc.posting_date) frm.set_value("due_date", frappe.datetime.add_days(frm.doc.posting_date, 30));
	},

	set_total(frm) {
		let total = 0;
		(frm.doc.items || []).forEach((item) => (total += flt(item.amount)));
		frm.set_value("grand_total", total);
	},
});

frappe.ui.form.on("Purchase Invoice Item", {
	qty: (frm, cdt, cdn) => set_amount(frm, cdt, cdn),
	rate: (frm, cdt, cdn) => set_amount(frm, cdt, cdn),
	items_remove: (frm) => frm.trigger("set_total"),
	item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item_code || !frm.doc.company) return;
		frappe
			.call("spend.spend.doctype.item.item.get_item_details", { item_code: row.item_code, company: frm.doc.company, supplier: frm.doc.supplier })
			.then(({ message: d }) => {
				const values = { item_name: d.item_name, description: d.description, stock_uom: d.stock_uom, uom: d.uom, conversion_factor: d.conversion_factor, rate: d.rate, is_fixed_asset: d.is_fixed_asset };
				if (d.is_fixed_asset) Object.assign(values, { expense_category: "", expense_sub_category: "" });
				values.expense_account = d.expense_account;
				if (d.cost_center && !row.cost_center) values.cost_center = d.cost_center;
				frappe.model.set_value(cdt, cdn, values);
			});
	},
	uom(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item_code || !row.uom) return;
		const previous = flt(row.conversion_factor) || 1;
		frappe.call("spend.spend.doctype.item.item.get_uom_details", { item_code: row.item_code, uom: row.uom }).then(({ message }) => {
			frappe.model.set_value(cdt, cdn, { conversion_factor: message.conversion_factor, rate: (flt(row.rate) / previous) * message.conversion_factor });
		});
	},
	conversion_factor: (frm, cdt, cdn) => set_amount(frm, cdt, cdn),
	items_add(frm, cdt, cdn) {
		if (frm.doc.cost_center) frappe.model.set_value(cdt, cdn, "cost_center", frm.doc.cost_center);
		if (frm.doc.project) frappe.model.set_value(cdt, cdn, "project", frm.doc.project);
	},
});

function set_amount(frm, cdt, cdn) {
	const item = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, { amount: flt(item.qty) * flt(item.rate), stock_qty: flt(item.qty) * flt(item.conversion_factor || 1) });
	frm.trigger("set_total");
}

// a category fills in its expense account
frappe.ui.form.on("Purchase Invoice Item", {
	expense_category(frm, cdt, cdn) {
		frappe.model.set_value(cdt, cdn, "expense_sub_category", "");
		set_item_category_account(cdt, cdn);
	},
	expense_sub_category(frm, cdt, cdn) {
		set_item_category_account(cdt, cdn);
	},
});

function set_item_category_account(cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.expense_category && !row.expense_sub_category) return;
	frappe
		.call("spend.spend.expense_category.get_category_account", { category: row.expense_category, sub_category: row.expense_sub_category })
		.then(({ message }) => message && frappe.model.set_value(cdt, cdn, "expense_account", message));
}
