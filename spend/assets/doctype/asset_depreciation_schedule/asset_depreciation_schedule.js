// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Asset Depreciation Schedule", {
	refresh(frm) {
		frm.disable_save();
		if (frm.doc.docstatus === 1 && frm.doc.status === "Active" && frappe.model.can_submit("Asset")) {
			frm.add_custom_button(__("Post Due Depreciation"), () =>
				frappe
					.call({
						method: "spend.assets.doctype.asset_depreciation_schedule.asset_depreciation_schedule.post_depreciation",
						args: { schedule: frm.doc.name },
						freeze: true,
					})
					.then(({ message }) => {
						frappe.show_alert({ message: __("{0} depreciation entries posted", [message.length]), indicator: "green" });
						frm.reload_doc();
					})
			);
		}
		frm.add_custom_button(__("Asset"), () => frappe.set_route("Form", "Asset", frm.doc.asset));
	},
});
