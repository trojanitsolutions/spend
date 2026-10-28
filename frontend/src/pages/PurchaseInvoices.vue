<template>
	<div>
		<PageHeader title="Bills" subtitle="Supplier invoices, posted to expense and payable accounts">
			<template #actions>
				<Button v-if="can('Purchase Invoice', 'create')" v-tour="'bills.new'" variant="solid" icon-left="lucide-plus" label="New Bill" @click="$router.push('/bills/new')" />
			</template>
		</PageHeader>

		<div class="grid grid-cols-2 gap-3 p-4 sm:grid-cols-3 sm:px-6">
			<StatCard label="Open bills" :value="open.length" />
			<StatCard label="Outstanding" :value="fmt(open.reduce((t, r) => t + r.outstanding_amount, 0))" />
			<StatCard label="Overdue" :value="fmt(overdue)" :tone="overdue > 0 ? 'red' : undefined" />
		</div>

		<div class="flex flex-wrap gap-2 px-4 pb-2 sm:px-6">
			<div class="max-w-full overflow-x-auto"><TabButtons v-model="status" :options="STATUSES.map((s) => ({ label: s, value: s }))" /></div>
			<div class="w-full sm:ml-auto sm:w-64">
				<TextInput v-model="query" type="search" placeholder="Search supplier or bill no." :debounce="150">
					<template #prefix><span class="lucide-search size-4 text-ink-gray-5" aria-hidden="true" /></template>
				</TextInput>
			</div>
		</div>
		<FilterBar v-model="filters" :fields="FILTERS" />

		<DataTable :columns="columns" :rows="filtered" :loading="loading" clickable empty-text="No bills match" @row-click="(r) => $router.push(`/bills/${r.name}`)">
			<template #supplier="{ row }">
				<div class="font-medium text-ink-gray-9">{{ row.supplier }}</div>
				<div class="text-sm text-ink-gray-5">{{ row.name }}<template v-if="row.bill_no"> · {{ row.bill_no }}</template></div>
			</template>
			<template #due_date="{ row }">
				<span :class="row.status === 'Overdue' ? 'text-ink-red-4' : ''">{{ date(row.due_date) }}</span>
			</template>
			<template #status="{ row }"><StatusBadge :status="approvalLabel(row.docstatus, row.workflow_state, row.status)" /></template>
		</DataTable>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { Button, TabButtons, TextInput } from "frappe-ui"
import DataTable, { type Column } from "@/components/DataTable.vue"
import FilterBar from "@/components/FilterBar.vue"
import PageHeader from "@/components/PageHeader.vue"
import StatCard from "@/components/StatCard.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import { getList } from "@/api"
import { type FilterField, toServerFilters, useListFilters } from "@/filters"
import { approvalLabel, date, money } from "@/format"
import { can, currency, session } from "@/store"

const STATUSES = ["All", "Draft", "Unpaid", "Partly Paid", "Overdue", "Paid", "Cancelled"]

const FILTERS: FilterField[] = [
	{ key: "posting_date", label: "Bill date", type: "date-range" },
	{ key: "supplier", label: "Supplier", type: "link", doctype: "Supplier" },
	{ key: "project", label: "Project", type: "link", doctype: "Project", child: "Purchase Invoice Item", filters: { company: session.company } },
	{ key: "cost_center", label: "Cost center", type: "link", doctype: "Cost Center", child: "Purchase Invoice Item", filters: { company: session.company, is_group: 0 } },
]

const filters = useListFilters(FILTERS)
const rows = ref<any[]>([])
const loading = ref(true)
const status = ref("All")
const query = ref("")
const fmt = (v: number) => money(v, currency.value)

const columns: Column[] = [
	{ key: "supplier", label: "Supplier" },
	{ key: "posting_date", label: "Date", format: date },
	{ key: "due_date", label: "Due" },
	{ key: "status", label: "Status" },
	{ key: "grand_total", label: "Total", align: "right", format: (v) => fmt(v) },
	{ key: "outstanding_amount", label: "Outstanding", align: "right", format: (v, r) => (r.docstatus === 1 ? fmt(v) : "—") },
]

const open = computed(() => rows.value.filter((r) => r.docstatus === 1 && r.outstanding_amount > 0))
const overdue = computed(() => open.value.filter((r) => r.status === "Overdue").reduce((t, r) => t + r.outstanding_amount, 0))
const filtered = computed(() => {
	const q = query.value.trim().toLowerCase()
	return rows.value.filter(
		(r) =>
			(status.value === "All" || r.status === status.value) &&
			(!q || `${r.supplier} ${r.name} ${r.bill_no || ""}`.toLowerCase().includes(q)),
	)
})

async function load() {
	loading.value = true
	try {
		rows.value = await getList(
			"Purchase Invoice",
			["name", "supplier", "bill_no", "posting_date", "due_date", "status", "docstatus", "workflow_state", "grand_total", "outstanding_amount"],
			toServerFilters("Purchase Invoice", FILTERS, filters, { company: session.company }),
			"posting_date desc, creation desc",
			500,
		)
	} finally {
		loading.value = false
	}
}

onMounted(load)
watch(filters, load)
</script>
