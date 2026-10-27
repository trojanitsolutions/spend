// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.listview_settings["Journal Entry"] = {
	add_fields: ["voucher_type", "total_debit", "currency"],
	get_indicator(doc) {
		if (doc.docstatus === 2) return [__("Cancelled"), "gray", "docstatus,=,2"];
		if (doc.docstatus === 0) return [__("Draft"), "red", "docstatus,=,0"];
		const color = { "Depreciation Entry": "purple", "Asset Capitalization": "cyan", "Expense Entry": "orange" }[doc.voucher_type] || "blue";
		return [__(doc.voucher_type), color, "voucher_type,=," + doc.voucher_type];
	},
};
