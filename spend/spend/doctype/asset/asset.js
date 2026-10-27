// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Asset", {
	setup(frm) {
		const ledger = (root_types, extra = {}) => () => ({
			filters: { company: frm.doc.company, is_group: 0, disabled: 0, root_type: ["in", root_types], ...extra },
		});
		frm.set_query("fixed_asset_account", ledger(["Asset"], { account_type: "Fixed Asset" }));
		frm.set_query("accumulated_depreciation_account", ledger(["Asset"], { account_type: "Accumulated Depreciation" }));
		frm.set_query("depreciation_expense_account", ledger(["Expense"]));
		frm.set_query("capitalization_credit_account", ledger(["Asset", "Liability", "Equity"]));
		frm.set_query("cost_center", () => ({ filters: { company: frm.doc.company, is_group: 0, disabled: 0 } }));
		frm.ignore_doctypes_on_cancel_all = ["Asset Depreciation Schedule", "Journal Entry", "GL Entry"];
	},

	refresh(frm) {
		frm.trigger("show_book_value");
		frm.trigger("show_schedule");
		if (frm.doc.docstatus !== 1) return;

		if (frm.doc.depreciation_schedule) {
			frm.add_custom_button(__("Depreciation Schedule"), () =>
				frappe.set_route("Form", "Asset Depreciation Schedule", frm.doc.depreciation_schedule), __("View"));
		}
		frm.add_custom_button(__("Ledger"), () =>
			frappe.set_route("List", "GL Entry", { reference_name: frm.doc.name, is_cancelled: 0 }), __("View"));
		frm.add_custom_button(__("Journal Entries"), () =>
			frappe.set_route("List", "Journal Entry", { asset: frm.doc.name }), __("View"));

		if (frm.doc.calculate_depreciation && frm.doc.status !== "Fully Depreciated" && frm.perm[0]?.submit) {
			frm.add_custom_button(__("Post Due Depreciation"), () => {
				frappe
					.call({
						method: "spend.spend.depreciation.post_due_depreciation",
						args: { asset: frm.doc.name },
						freeze: true,
					})
					.then(({ message }) => {
						frappe.show_alert({
							message: message.length
								? __("{0} depreciation entries posted", [message.length])
								: __("No depreciation is due yet"),
							indicator: message.length ? "green" : "blue",
						});
						frm.reload_doc();
					});
			});
		}
	},

	company(frm) {
		if (!frm.doc.company) return;
		frappe.call("spend.spend.doctype.company.company.get_company_defaults", { company: frm.doc.company }).then(({ message }) => {
			if (!message) return;
			frm.set_value({
				fixed_asset_account: message.fixed_asset_account,
				accumulated_depreciation_account: message.accumulated_depreciation_account,
				depreciation_expense_account: message.depreciation_expense_account,
				cost_center: message.default_cost_center,
				capitalization_credit_account: frm.doc.capitalization_credit_account || message.default_payable_account,
			});
		});
	},

	available_for_use_date(frm) {
		if (!frm.doc.purchase_date && frm.doc.available_for_use_date) {
			frm.set_value("purchase_date", frm.doc.available_for_use_date);
		}
	},

	show_book_value(frm) {
		if (frm.doc.docstatus !== 1 || !frm.doc.calculate_depreciation) return;
		const gross = flt(frm.doc.gross_purchase_amount);
		const depreciable = gross - flt(frm.doc.salvage_value);
		const pct = depreciable > 0 ? (flt(frm.doc.accumulated_depreciation) / depreciable) * 100 : 0;
		frm.dashboard.add_progress(
			__("Depreciated"),
			pct,
			__("Book value {0} of {1}", [
				format_currency(frm.doc.value_after_depreciation, frm.doc.currency),
				format_currency(gross, frm.doc.currency),
			])
		);
	},

	show_schedule(frm) {
		if (!frm.doc.depreciation_schedule || frm.is_dirty()) return;
		frappe.call("spend.spend.doctype.asset.asset.get_schedule_preview", { asset: frm.doc.name }).then(({ message }) => {
			if (!message?.length) return;
			const cur = (v) => format_currency(v, frm.doc.currency);
			const rows = message
				.map(
					(r) => `<tr>
						<td>${frappe.datetime.str_to_user(r.schedule_date)}</td>
						<td class="text-right">${cur(r.opening_book_value)}</td>
						<td class="text-right">${cur(r.depreciation_amount)}</td>
						<td class="text-right">${cur(r.accumulated_depreciation_amount)}</td>
						<td class="text-right">${cur(r.closing_book_value)}</td>
						<td>${r.journal_entry ? `<a href="/app/journal-entry/${r.journal_entry}">${r.journal_entry}</a>` : '<span class="text-muted">' + __("Not posted") + "</span>"}</td>
					</tr>`
				)
				.join("");
			frm.dashboard.add_section(
				`<div class="table-responsive" style="max-height: 320px; overflow:auto">
					<table class="table table-sm table-hover small">
						<thead><tr>
							<th>${__("Date")}</th><th class="text-right">${__("Opening")}</th>
							<th class="text-right">${__("Depreciation")}</th><th class="text-right">${__("Accumulated")}</th>
							<th class="text-right">${__("Closing")}</th><th>${__("Entry")}</th>
						</tr></thead>
						<tbody>${rows}</tbody>
					</table>
				</div>`,
				__("Depreciation Schedule")
			);
			frm.dashboard.show();
		});
	},
});
