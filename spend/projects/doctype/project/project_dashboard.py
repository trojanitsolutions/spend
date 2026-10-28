from frappe import _


def get_data():
	return {
		"fieldname": "project",
		"transactions": [
			{"label": _("Work"), "items": ["Task"]},
			{"label": _("Spend"), "items": ["Journal Entry", "Purchase Invoice", "Supplier Payment", "Recurring Payment"]},
		],
	}
