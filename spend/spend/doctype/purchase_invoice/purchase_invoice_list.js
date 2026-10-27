// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.listview_settings["Purchase Invoice"] = {
	add_fields: ["status", "outstanding_amount", "due_date"],
	get_indicator(doc) {
		const colors = { Draft: "red", Unpaid: "orange", "Partly Paid": "yellow", Paid: "green", Overdue: "red", Cancelled: "gray" };
		return [__(doc.status), colors[doc.status] || "gray", `status,=,${doc.status}`];
	},
};
