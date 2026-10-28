// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.listview_settings["Asset"] = {
	add_fields: ["status", "value_after_depreciation"],
	get_indicator(doc) {
		const colors = {
			Draft: "red",
			Submitted: "blue",
			"Partially Depreciated": "orange",
			"Fully Depreciated": "green",
			Cancelled: "gray",
		};
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
};
