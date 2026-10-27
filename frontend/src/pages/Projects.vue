<template>
	<div>
		<PageHeader title="Projects" subtitle="Budget and spend for each piece of work">
			<template #actions>
				<Button icon-left="lucide-chart-column" label="Project Spend" @click="$router.push('/reports/project-spend')" />
				<Button v-if="can('Project', 'create')" variant="solid" icon-left="lucide-plus" label="New Project" @click="$router.push('/projects/new')" />
			</template>
		</PageHeader>

		<div class="grid grid-cols-2 gap-3 p-4 sm:px-6 lg:grid-cols-4">
			<StatCard label="Open projects" :value="open.length" />
			<StatCard label="Budget (open)" :value="fmt(sum(open, 'budget_amount'))" />
			<StatCard label="Spent (open)" :value="fmt(sum(open, 'spent'))" />
			<StatCard label="Over budget" :value="overBudget" :tone="overBudget ? 'red' : undefined" />
		</div>

		<div class="flex flex-wrap gap-2 px-4 pb-2 sm:px-6">
			<div class="max-w-full overflow-x-auto"><TabButtons v-model="view" :options="VIEWS.map((v) => ({ label: v, value: v }))" /></div>
			<div class="w-full sm:ml-auto sm:w-64">
				<TextInput v-model="query" type="search" placeholder="Search projects" :debounce="150">
					<template #prefix><span class="lucide-search size-4 text-ink-gray-5" aria-hidden="true" /></template>
				</TextInput>
			</div>
		</div>
		<FilterBar v-model="filters" :fields="FILTERS" />

		<DataTable :columns="columns" :rows="filtered" :loading="loading" clickable empty-text="No projects match" @row-click="(r) => $router.push(`/projects/${r.name}`)">
			<template #project_name="{ row }">
				<div class="font-medium text-ink-gray-9">{{ row.project_name }}</div>
				<div class="text-sm text-ink-gray-5">{{ row.name }}<template v-if="row.end_date"> · ends {{ date(row.end_date) }}</template></div>
			</template>
			<template #status="{ value }"><StatusBadge :status="value" /></template>
			<template #utilization="{ row }">
				<div class="w-44">
					<UsageBar v-if="row.utilization !== null" :value="row.utilization" :caption="`${fmt(row.spent)} / ${fmt(row.budget_amount)}`" />
					<span v-else class="text-sm text-ink-gray-5">{{ fmt(row.spent) }} · no budget</span>
				</div>
			</template>
			<template #remaining="{ value }">
				<span v-if="value === null" class="text-ink-gray-5">—</span>
				<span v-else :class="value < 0 ? 'text-ink-red-4' : ''">{{ fmt(value) }}</span>
			</template>
		</DataTable>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { Button, TabButtons, TextInput } from "frappe-ui"
import DataTable, { type Column } from "@/components/DataTable.vue"
import FilterBar from "@/components/FilterBar.vue"
import PageHeader from "@/components/PageHeader.vue"
import StatCard from "@/components/StatCard.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import UsageBar from "@/components/UsageBar.vue"
import { api } from "@/api"
import { type FilterField, matchRow, overlaps, useListFilters } from "@/filters"
import { date, money } from "@/format"
import { can, currency, session } from "@/store"

const VIEWS = ["Open", "Completed", "All"]

const FILTERS: FilterField[] = [
	{ key: "period", label: "Running", type: "date-range", match: overlaps("start_date", "end_date") },
	{ key: "cost_center", label: "Cost center", type: "link", doctype: "Cost Center", filters: { company: session.company } },
]

const filters = useListFilters(FILTERS)
const rows = ref<any[]>([])
const loading = ref(true)
const view = ref("Open")
const query = ref("")
const fmt = (v: number) => money(v, currency.value)

const columns: Column[] = [
	{ key: "project_name", label: "Project" },
	{ key: "status", label: "Status" },
	{ key: "utilization", label: "Spent vs budget" },
	{ key: "remaining", label: "Remaining", align: "right" },
	{ key: "outstanding", label: "Owed to suppliers", align: "right", format: (v) => (v ? fmt(v) : "—") },
]

const open = computed(() => rows.value.filter((r) => r.status === "Open"))
const overBudget = computed(() => open.value.filter((r) => r.remaining !== null && r.remaining < 0).length)
const filtered = computed(() => {
	const q = query.value.trim().toLowerCase()
	return rows.value.filter(
		(r) => (view.value === "All" || r.status === view.value) && matchRow(FILTERS, filters, r) && (!q || `${r.project_name} ${r.name}`.toLowerCase().includes(q)),
	)
})

function sum(list: any[], field: string) {
	return list.reduce((total, r) => total + Number(r[field] || 0), 0)
}

onMounted(async () => {
	try {
		rows.value = await api("spend.api.get_projects", { company: session.company })
	} finally {
		loading.value = false
	}
})
</script>
