<template>
	<div>
		<PageHeader title="Assets" subtitle="Fixed assets, book values and depreciation status">
			<template #actions>
				<Button icon-left="lucide-chart-column" label="Asset Register" @click="$router.push('/reports/asset-register')" />
				<Button v-if="can('Asset', 'create')" variant="solid" icon-left="lucide-plus" label="New Asset" @click="$router.push('/assets/new')" />
			</template>
		</PageHeader>

		<div class="grid grid-cols-2 gap-3 p-4 sm:grid-cols-4 sm:px-6">
			<StatCard label="Assets" :value="active.length" />
			<StatCard label="Gross value" :value="fmt(sum('gross_purchase_amount'))" />
			<StatCard label="Accumulated depreciation" :value="fmt(sum('accumulated_depreciation'))" />
			<StatCard label="Book value" :value="fmt(sum('value_after_depreciation'))" />
		</div>

		<div class="flex flex-wrap gap-2 px-4 pb-2 sm:px-6">
			<div class="max-w-full overflow-x-auto"><TabButtons v-model="status" :options="STATUSES.map((s) => ({ label: s, value: s }))" /></div>
			<div class="w-full sm:ml-auto sm:w-64">
				<TextInput v-model="query" type="search" placeholder="Search assets" :debounce="150">
					<template #prefix><span class="lucide-search size-4 text-ink-gray-5" aria-hidden="true" /></template>
				</TextInput>
			</div>
		</div>
		<FilterBar v-model="filters" :fields="FILTERS" />

		<DataTable :columns="columns" :rows="filtered" :loading="loading" clickable empty-text="No assets match" @row-click="(r) => $router.push(`/assets/${r.name}`)">
			<template #asset_name="{ row }">
				<div class="font-medium text-ink-gray-9">{{ row.asset_name }}</div>
				<div class="text-sm text-ink-gray-5">{{ row.name }}</div>
			</template>
			<template #status="{ value }"><StatusBadge :status="value" /></template>
			<template #progress="{ row }">
				<div class="w-28"><UsageBar neutral :value="depreciatedPct(row)" /></div>
			</template>
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
import UsageBar from "@/components/UsageBar.vue"
import { getList } from "@/api"
import { type FilterField, toServerFilters, useListFilters } from "@/filters"
import { date, money } from "@/format"
import { can, currency, session } from "@/store"

const STATUSES = ["All", "Draft", "Submitted", "Partially Depreciated", "Fully Depreciated", "Cancelled"]

const FILTERS: FilterField[] = [
	{ key: "available_for_use_date", label: "Capitalized", type: "date-range" },
	{ key: "cost_center", label: "Cost center", type: "link", doctype: "Cost Center", filters: { company: session.company, is_group: 0 } },
]

const filters = useListFilters(FILTERS)
const rows = ref<any[]>([])
const loading = ref(true)
const status = ref("All")
const query = ref("")
const fmt = (v: number) => money(v, currency.value)

const columns: Column[] = [
	{ key: "asset_name", label: "Asset" },
	{ key: "status", label: "Status" },
	{ key: "cost_center", label: "Cost Center" },
	{ key: "available_for_use_date", label: "Capitalized", format: date },
	{ key: "depreciation_method", label: "Method", format: (v, r) => (r.calculate_depreciation ? v : "—") },
	{ key: "gross_purchase_amount", label: "Gross", align: "right", format: (v) => fmt(v) },
	{ key: "value_after_depreciation", label: "Book Value", align: "right", format: (v) => fmt(v) },
	{ key: "progress", label: "Depreciated" },
]

const active = computed(() => rows.value.filter((r) => r.docstatus === 1))
const filtered = computed(() => {
	const q = query.value.trim().toLowerCase()
	return rows.value.filter(
		(r) =>
			(status.value === "All" || r.status === status.value) &&
			(!q || `${r.asset_name} ${r.name} ${r.location || ""}`.toLowerCase().includes(q)),
	)
})

function sum(field: string) {
	return active.value.reduce((total, r) => total + Number(r[field] || 0), 0)
}

function depreciatedPct(row: any) {
	const depreciable = row.gross_purchase_amount - row.salvage_value
	return depreciable > 0 ? (row.accumulated_depreciation / depreciable) * 100 : 0
}

async function load() {
	loading.value = true
	try {
		rows.value = await getList(
			"Asset",
			[
				"name", "asset_name", "status", "docstatus", "cost_center", "location", "available_for_use_date",
				"calculate_depreciation", "depreciation_method", "gross_purchase_amount", "salvage_value",
				"accumulated_depreciation", "value_after_depreciation",
			],
			toServerFilters("Asset", FILTERS, filters, { company: session.company }),
			"creation desc",
			500,
		)
	} finally {
		loading.value = false
	}
}

onMounted(load)
watch(filters, load)
</script>
