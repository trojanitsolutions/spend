// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Supplier Payment", {
	setup(frm) {
		const ledger = (extra) => () => ({ filters: { company: frm.doc.company, is_group: 0, disabled: 0, ...extra } });
		frm.set_query("paid_from", ledger({ account_type: ["in", ["Cash", "Bank"]] }));
		frm.set_query("paid_to", ledger({ account_type: "Payable" }));
		frm.set_query("purchase_invoice", "references", () => ({
			filters: {
				supplier: frm.doc.supplier,
				company: frm.doc.company,
				docstatus: 1,
				outstanding_amount: [">", 0],
				...(frm.doc.project ? { project: frm.doc.project } : {}),
			},
		}));
		frm.set_query("project", () => ({ filters: { company: frm.doc.company } }));
		frm.ignore_doctypes_on_cancel_all = ["GL Entry", "Purchase Invoice"];
	},

	refresh(frm) {
		if (frm.doc.docstatus === 0 && frm.doc.supplier) {
			frm.add_custom_button(__("Get Outstanding Bills"), () => frm.trigger("get_outstanding_bills"));
		}
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Ledger"), () => frappe.set_route("List", "GL Entry", { voucher_no: frm.doc.name }));
		}
	},

	company(frm) {
		if (!frm.doc.company) return;
		frappe.db
			.get_value("Company", frm.doc.company, ["default_payable_account", "default_cash_account"])
			.then(({ message }) => {
				frm.set_value("paid_to", message.default_payable_account);
				if (!frm.doc.paid_from) frm.set_value("paid_from", message.default_cash_account);
			});
	},

	supplier(frm) {
		frm.refresh();
	},

	get_outstanding_bills(frm) {
		if (!frm.doc.supplier || !frm.doc.company) {
			frappe.msgprint(__("Select a Supplier and Company first"));
			return;
		}
		frappe
			.call("spend.spend.doctype.supplier_payment.supplier_payment.get_outstanding_invoices", {
				supplier: frm.doc.supplier,
				company: frm.doc.company,
				project: frm.doc.project,
			})
			.then(({ message }) => {
				frm.clear_table("references");
				let remaining = flt(frm.doc.paid_amount);
				const fill = !remaining;
				(message || []).forEach((bill) => {
					const allocated = fill ? bill.outstanding_amount : Math.min(remaining, bill.outstanding_amount);
					if (!fill && allocated <= 0) return;
					remaining -= allocated;
					frm.add_child("references", {
						purchase_invoice: bill.name,
						due_date: bill.due_date,
						grand_total: bill.grand_total,
						outstanding_amount: bill.outstanding_amount,
						allocated_amount: allocated,
					});
				});
				frm.refresh_field("references");
				frm.trigger("set_total");
				if (fill) frm.set_value("paid_amount", frm.doc.total_allocated);
			});
	},

	set_total(frm) {
		let total = 0;
		(frm.doc.references || []).forEach((row) => (total += flt(row.allocated_amount)));
		frm.set_value("total_allocated", total);
	},
});

frappe.ui.form.on("Supplier Payment Reference", {
	allocated_amount: (frm) => frm.trigger("set_total"),
	references_remove: (frm) => frm.trigger("set_total"),
});
