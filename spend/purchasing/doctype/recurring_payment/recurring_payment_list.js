// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.listview_settings["Recurring Payment"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colors = { Draft: "red", Active: "blue", Stopped: "orange", Completed: "green", Cancelled: "gray" };
		return [__(doc.status), colors[doc.status] || "gray", `status,=,${doc.status}`];
	},
};
