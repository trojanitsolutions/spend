<template>
	<div>
		<PageHeader title="Budgets" subtitle="Allocated versus actual spending, per cost center">
			<template #actions>
				<div class="w-44">
					<FormControl v-model="fiscalYear" type="select" :options="session.fiscalYears.map((f) => f.name)" aria-label="Fiscal year" />
				</div>
				<Button v-if="can('Budget', 'create')" variant="solid" icon-left="lucide-plus" label="New Budget" @click="$router.push('/budgets/new')" />
			</template>
		</PageHeader>

		<div v-if="report" class="grid grid-cols-2 gap-3 p-4 sm:px-6 lg:grid-cols-4">
			<StatCard label="Allocated" :value="fmt(totals.allocated)" />
			<StatCard label="Spent" :value="fmt(totals.actual)" :tone="totals.utilization > 100 ? 'red' : undefined" />
			<StatCard label="Remaining" :value="fmt(totals.allocated - totals.actual)" :tone="totals.allocated - totals.actual < 0 ? 'red' : undefined" />
			<StatCard label="Utilization" :value="percent(totals.utilization)" :tone="totals.allocated ? utilizationTone(totals.utilization) : undefined" />
		</div>
		<FilterBar v-model="filters" :fields="FILTERS" />

		<DataTable
			:columns="columns"
			:rows="rows"
			row-key="budget"
			:loading="loading"
			clickable
			empty-text="No budgets for this fiscal year"
			@row-click="(r) => $router.push(`/budgets/${r.budget}`)"
		>
			<template #cost_center="{ row }">
				<div class="font-medium text-ink-gray-9">{{ row.cost_center }}</div>
				<div class="text-sm text-ink-gray-5">{{ row.budget }}</div>
			</template>
			<template #utilization="{ row }">
				<div class="w-40"><UsageBar :value="row.utilization" :caption="percent(row.utilization)" /></div>
			</template>
			<template #docstatus="{ row }"><StatusBadge :status="row.docstatus === 0 ? 'Draft' : row.utilization_status" /></template>
		</DataTable>
	</div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { Button, FormControl } from "frappe-ui"
import DataTable, { type Column } from "@/components/DataTable.vue"
import FilterBar from "@/components/FilterBar.vue"
import PageHeader from "@/components/PageHeader.vue"
import StatCard from "@/components/StatCard.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import UsageBar from "@/components/UsageBar.vue"
import { getList, runReport, type ReportResult } from "@/api"
import { type FilterField, matchRow, useListFilters } from "@/filters"
import { money, percent, utilizationTone } from "@/format"
import { can, currency, session } from "@/store"

const FILTERS: FilterField[] = [
	{ key: "cost_center", label: "Cost center", type: "link", doctype: "Cost Center", filters: { company: session.company } },
]

const filters = useListFilters(FILTERS)
const fiscalYear = ref(session.currentFiscalYear || session.fiscalYears[0]?.name || "")
const report = ref<ReportResult | null>(null)
const drafts = ref<any[]>([])
const loading = ref(false)
const fmt = (v: number) => money(v, currency.value)

const columns: Column[] = [
	{ key: "cost_center", label: "Cost Center" },
	{ key: "budget_period", label: "Period" },
	{ key: "allocated", label: "Allocated", align: "right", format: (v) => fmt(v) },
	{ key: "actual", label: "Spent", align: "right", format: (v) => fmt(v) },
	{ key: "remaining", label: "Remaining", align: "right", format: (v) => fmt(v) },
	{ key: "utilization", label: "Utilization" },
	{ key: "docstatus", label: "Status" },
]

const submitted = computed(() => (report.value?.result || []).filter((r) => matchRow(FILTERS, filters, r)))
const rows = computed(() => [
	...submitted.value.map((r) => ({ ...r, docstatus: 1 })),
	...drafts.value.filter((d) => matchRow(FILTERS, filters, d)).map((d) => ({
		budget: d.name,
		cost_center: d.cost_center,
		budget_period: d.budget_period,
		allocated: d.total_budget,
		actual: 0,
		remaining: d.total_budget,
		utilization: 0,
		docstatus: 0,
	})),
])

const totals = computed(() => {
	const allocated = submitted.value.reduce((t, r) => t + r.allocated, 0)
	const actual = submitted.value.reduce((t, r) => t + r.actual, 0)
	return { allocated, actual, utilization: allocated ? (actual / allocated) * 100 : 0 }
})

async function load() {
	if (!fiscalYear.value) return
	loading.value = true
	try {
		const filters = { company: session.company, fiscal_year: fiscalYear.value }
		;[report.value, drafts.value] = await Promise.all([
			runReport("Budget Utilization", filters),
			getList("Budget", ["name", "cost_center", "budget_period", "total_budget"], { ...filters, docstatus: 0 }),
		])
	} finally {
		loading.value = false
	}
}

watch(fiscalYear, load, { immediate: true })
</script>
