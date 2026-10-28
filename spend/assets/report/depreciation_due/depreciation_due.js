// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.query_reports["Depreciation Due"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{ fieldname: "as_on_date", label: __("As On Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{
			fieldname: "cost_center",
			label: __("Cost Center"),
			fieldtype: "Link",
			options: "Cost Center",
			get_query: () => ({ filters: { company: frappe.query_report.get_filter_value("company") } }),
		},
		{
			fieldname: "asset",
			label: __("Asset"),
			fieldtype: "Link",
			options: "Asset",
			get_query: () => ({ filters: { company: frappe.query_report.get_filter_value("company") } }),
		},
	],
	onload(report) {
		if (!frappe.model.can_submit("Journal Entry")) return;
		report.page.add_inner_button(__("Post Due Depreciation"), () => {
			const company = report.get_filter_value("company");
			const date = report.get_filter_value("as_on_date");
			frappe.confirm(__("Post all depreciation due on or before {0} for {1}?", [frappe.datetime.str_to_user(date), company]), () =>
				frappe
					.call({
						method: "spend.spend.depreciation.post_due_depreciation",
						args: { company, date },
						freeze: true,
						freeze_message: __("Posting depreciation..."),
					})
					.then(({ message }) => {
						frappe.show_alert({ message: __("{0} depreciation entries posted", [message.length]), indicator: "green" });
						report.refresh();
					})
			);
		});
	},
};
