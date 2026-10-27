// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.listview_settings["GL Entry"] = {
	add_fields: ["is_cancelled"],
	filters: [["is_cancelled", "=", 0]],
	get_indicator(doc) {
		return doc.is_cancelled ? [__("Cancelled"), "gray", "is_cancelled,=,1"] : [__("Posted"), "green", "is_cancelled,=,0"];
	},
};
