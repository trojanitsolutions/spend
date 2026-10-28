<template>
	<div>
		<PageHeader :title="page.title" :subtitle="page.subtitle">
			<template #actions>
				<Button v-if="can('Journal Entry', 'create')" v-tour="`${page.path.slice(1)}.new`" variant="solid" icon-left="lucide-plus" :label="page.newLabel" @click="$router.push(`${page.path}/new`)" />
			</template>
		</PageHeader>

		<div class="flex flex-wrap gap-2 px-4 py-3 sm:px-6">
			<div class="max-w-full overflow-x-auto"><TabButtons v-model="type" :options="page.types.map((t) => ({ label: t === 'All' ? 'All' : (LABELS[t] ?? t), value: t }))" /></div>
		</div>
		<FilterBar v-model="filters" :fields="FILTERS" />

		<DataTable :columns="columns" :rows="rows" :loading="loading" clickable :empty-text="page.empty" @row-click="open">
			<template #title="{ row }">
				<div class="max-w-72 truncate font-medium text-ink-gray-9">{{ row.title }}</div>
				<div class="text-sm text-ink-gray-5">{{ row.name }}</div>
			</template>
			<template #voucher_type="{ value }"><StatusBadge :status="value" /></template>
			<template #docstatus="{ row }"><StatusBadge :status="approvalLabel(row.docstatus, row.workflow_state)" /></template>
		</DataTable>
		<div v-if="rows.length === limit" class="p-4 text-center">
			<Button label="Load more" @click="loadMore" />
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { Button, TabButtons } from "frappe-ui"
import DataTable, { type Column } from "@/components/DataTable.vue"
import FilterBar from "@/components/FilterBar.vue"
import PageHeader from "@/components/PageHeader.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import { getList } from "@/api"
import { docstatusFilter, type FilterField, toServerFilters, useListFilters } from "@/filters"
import { EXPENSE_TYPES, approvalLabel, date, entryPath, money } from "@/format"
import { can, currency, session } from "@/store"

const JOURNAL_TYPES = ["Journal Entry", "Depreciation Entry", "Asset Capitalization"]
const PAGES = {
	expense: {
		title: "Expenses",
		subtitle: "Money spent from cash or bank, booked to expense accounts and projects",
		newLabel: "Record Expense",
		path: "/expenses",
		empty: "No expenses yet",
		types: ["All", ...EXPENSE_TYPES],
	},
	journal: {
		title: "Journal Entries",
		subtitle: "Balanced debit and credit entries: adjustments, depreciation and capitalization",
		newLabel: "New Journal Entry",
		path: "/journals",
		empty: "No journal entries yet",
		types: ["All", ...JOURNAL_TYPES],
	},
}
// tab names on this page
const LABELS: Record<string, string> = { "Expense Entry": "Recorded", "Recurring Payment": "Recurring", "Journal Entry": "Manual" }

const props = defineProps<{ kind: "expense" | "journal" }>()
const page = computed(() => PAGES[props.kind])

const LINE = "Journal Entry Account"
const FILTERS: FilterField[] = [
	{ key: "posting_date", label: "Date", type: "date-range" },
	docstatusFilter,
	{ key: "project", label: "Project", type: "link", doctype: "Project", child: LINE, filters: { company: session.company } },
	{ key: "cost_center", label: "Cost center", type: "link", doctype: "Cost Center", child: LINE, filters: { company: session.company, is_group: 0 } },
	{ key: "account", label: "Account", type: "link", doctype: "Account", child: LINE, filters: { company: session.company, is_group: 0 } },
]

const router = useRouter()
const filters = useListFilters(FILTERS)
const type = ref("All")
const rows = ref<any[]>([])
const loading = ref(false)
const limit = ref(50)
const fmt = (v: number) => money(v, currency.value)

const columns: Column[] = [
	{ key: "posting_date", label: "Date", format: date },
	{ key: "title", label: "Description" },
	{ key: "voucher_type", label: "Type" },
	{ key: "docstatus", label: "Status" },
	{ key: "total_debit", label: "Amount", align: "right", format: (v) => fmt(v) },
]

async function load() {
	loading.value = true
	try {
		const base: Record<string, any> = { company: session.company }
		base.voucher_type = type.value === "All" ? ["in", page.value.types.slice(1)] : type.value
		rows.value = await getList(
			"Journal Entry",
			["name", "title", "voucher_type", "posting_date", "total_debit", "docstatus", "workflow_state"],
			toServerFilters("Journal Entry", FILTERS, filters, base),
			"posting_date desc, creation desc",
			limit.value,
		)
	} finally {
		loading.value = false
	}
}

function loadMore() {
	limit.value += 50
	load()
}

function open(row: any) {
	router.push(entryPath(row.name, row.voucher_type))
}

// the two pages share this component, so moving between them resets the tab
watch(
	() => props.kind,
	() => (type.value = "All"),
)

watch([type, filters, () => props.kind], () => {
	limit.value = 50
	load()
}, { immediate: true })
</script>
