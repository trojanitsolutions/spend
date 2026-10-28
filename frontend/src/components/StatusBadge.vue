<template>
	<Badge :theme="theme" :label="status" />
</template>

<script setup lang="ts">
import { computed } from "vue"
import { Badge } from "frappe-ui"
import { ASSET_STATUS_THEME } from "@/format"

type Theme = "gray" | "blue" | "green" | "amber" | "red" | "violet"

const EXTRA: Record<string, Theme> = {
	Active: "blue",
	"Pending GM Approval": "amber",
	Approved: "green",
	Rejected: "red",
	Open: "blue",
	Stopped: "amber",
	Skipped: "gray",
	"Recurring Payment": "blue",
	Completed: "green",
	Posted: "green",
	Due: "amber",
	Upcoming: "gray",
	"On Track": "green",
	"Near Limit": "amber",
	Exceeded: "red",
	"Depreciation Entry": "violet",
	"Asset Capitalization": "blue",
	"Expense Entry": "amber",
	"Journal Entry": "gray",
	Unpaid: "amber",
	"Partly Paid": "blue",
	Paid: "green",
	Overdue: "red",
	Working: "violet",
	"Pending Review": "amber",
	"Not Yet Due": "gray",
}

const props = defineProps<{ status: string }>()
const theme = computed<Theme>(() => ASSET_STATUS_THEME[props.status] || EXTRA[props.status] || "gray")
</script>
