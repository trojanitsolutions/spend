// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Task", {
	setup(frm) {
		frm.set_query("project", () => ({ filters: { status: "Open" } }));
		frm.set_query("parent_task", () => ({ filters: { project: frm.doc.project, is_group: 1, name: ["!=", frm.doc.name] } }));
		frm.set_query("task", "depends_on", () => ({ filters: { project: frm.doc.project, name: ["!=", frm.doc.name] } }));
	},

	refresh(frm) {
		if (frm.is_new() || ["Completed", "Cancelled"].includes(frm.doc.status)) return;
		frm.add_custom_button(__("Mark Completed"), () => {
			ask_completed_on((completed_on) => {
				frm.set_value({ status: "Completed", completed_on });
				frm.save();
			});
		});
	},
});

function ask_completed_on(callback) {
	frappe.prompt(
		[{ fieldname: "completed_on", fieldtype: "Date", label: __("Completed On"), default: frappe.datetime.get_today(), reqd: 1 }],
		({ completed_on }) => callback(completed_on),
		__("When was it done?"),
		__("Mark Completed")
	);
}
