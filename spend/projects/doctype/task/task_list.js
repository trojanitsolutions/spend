frappe.listview_settings["Task"] = {
	add_fields: ["status", "priority", "exp_end_date"],
	get_indicator(doc) {
		const colors = { Open: "orange", Working: "blue", "Pending Review": "purple", Overdue: "red", Completed: "green", Cancelled: "gray" };
		return [__(doc.status), colors[doc.status], `status,=,${doc.status}`];
	},
	onload(listview) {
		for (const status of ["Open", "Working", "Completed", "Cancelled"]) {
			listview.page.add_menu_item(__("Set as {0}", [__(status)]), () => {
				const names = listview.get_checked_items(true);
				if (!names.length) return frappe.msgprint(__("Select tasks first"));
				const set = (completed_on) =>
					frappe.call("spend.projects.doctype.task.task.set_multiple_status", { names, status, completed_on }).then(() => listview.refresh());
				if (status !== "Completed") return set();
				frappe.prompt(
					[{ fieldname: "completed_on", fieldtype: "Date", label: __("Completed On"), default: frappe.datetime.get_today(), reqd: 1 }],
					({ completed_on }) => set(completed_on),
					__("When was it done?"),
					__("Mark Completed")
				);
			});
		}
	},
};
