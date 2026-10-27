<template>
	<div>
		<PageHeader title="Payments" subtitle="Money paid to suppliers against their bills">
			<template #actions>
				<Button v-if="can('Supplier Payment', 'create')" variant="solid" icon-left="lucide-plus" label="Pay Supplier" @click="$router.push('/payments/new')" />
			</template>
		</PageHeader>

		<div class="grid grid-cols-2 gap-3 p-4 sm:px-6">
			<StatCard label="Payments" :value="submitted.length" />
			<StatCard label="Total paid" :value="fmt(submitted.reduce((t, r) => t + r.paid_amount, 0))" />
		</div>

		<div class="flex flex-wrap gap-2 px-4 pb-2 sm:px-6">
			<div class="w-full sm:ml-auto sm:w-64">
				<TextInput v-model="query" type="search" placeholder="Search supplier, reference or project" :debounce="150">
					<template #prefix><span class="lucide-search size-4 text-ink-gray-5" aria-hidden="true" /></template>
				</TextInput>
			</div>
		</div>
		<FilterBar v-model="filters" :fields="FILTERS" />

		<DataTable :columns="columns" :rows="filtered" :loading="loading" clickable empty-text="No payments yet" @row-click="(r) => $router.push(`/payments/${r.name}`)">
			<template #supplier="{ row }">
				<div class="font-medium text-ink-gray-9">{{ row.supplier }}</div>
				<div class="text-sm text-ink-gray-5">{{ row.name }}</div>
			</template>
			<template #docstatus="{ row }"><StatusBadge :status="approvalLabel(row.docstatus, row.workflow_state)" /></template>
			<template #actions="{ row }">
				<Button v-if="row.docstatus === 1 && can('Supplier Payment', 'cancel')" size="sm" theme="red" label="Cancel" @click.stop="confirmCancelPayment(row.name, load)" />
			</template>
		</DataTable>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { Button, TextInput } from "frappe-ui"
import DataTable, { type Column } from "@/components/DataTable.vue"
import FilterBar from "@/components/FilterBar.vue"
import PageHeader from "@/components/PageHeader.vue"
import StatCard from "@/components/StatCard.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import { getList } from "@/api"
import { docstatusFilter, type FilterField, toServerFilters, useListFilters } from "@/filters"
import { approvalLabel, date, money } from "@/format"
import { confirmCancelPayment } from "@/payments"
import { can, currency, session } from "@/store"

const FILTERS: FilterField[] = [
	{ key: "posting_date", label: "Date", type: "date-range" },
	docstatusFilter,
	{ key: "supplier", label: "Supplier", type: "link", doctype: "Supplier" },
	{ key: "project", label: "Project", type: "link", doctype: "Project", filters: { company: session.company } },
	{ key: "paid_from", label: "Paid from", type: "link", doctype: "Account", filters: { company: session.company, is_group: 0, account_type: ["in", ["Cash", "Bank"]] } },
]

const filters = useListFilters(FILTERS)
const rows = ref<any[]>([])
const loading = ref(true)
const query = ref("")
const fmt = (v: number) => money(v, currency.value)

const columns: Column[] = [
	{ key: "supplier", label: "Supplier" },
	{ key: "posting_date", label: "Date", format: date },
	{ key: "mode_of_payment", label: "Mode" },
	{ key: "paid_from", label: "Paid From" },
	{ key: "project", label: "Project", format: (v) => v || "—" },
	{ key: "reference_no", label: "Reference" },
	{ key: "docstatus", label: "Status" },
	{ key: "paid_amount", label: "Amount", align: "right", format: (v) => fmt(v) },
	{ key: "actions", label: "", align: "right" },
]

const submitted = computed(() => rows.value.filter((r) => r.docstatus === 1))
const filtered = computed(() => {
	const q = query.value.trim().toLowerCase()
	return rows.value.filter((r) => !q || `${r.supplier} ${r.name} ${r.reference_no || ""} ${r.project || ""}`.toLowerCase().includes(q))
})

async function load() {
	loading.value = true
	try {
		rows.value = await getList(
			"Supplier Payment",
			["name", "supplier", "posting_date", "mode_of_payment", "paid_from", "project", "reference_no", "docstatus", "workflow_state", "paid_amount"],
			toServerFilters("Supplier Payment", FILTERS, filters, { company: session.company }),
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
