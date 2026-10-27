<template>
	<div>
		<PageHeader title="Recurring Payments" subtitle="Rent, subscriptions and other regular costs, posted on their dates">
			<template #actions>
				<Button v-if="can('Recurring Payment', 'create')" variant="solid" icon-left="lucide-plus" label="New Recurring Payment" @click="$router.push('/recurring/new')" />
			</template>
		</PageHeader>

		<div class="grid grid-cols-2 gap-3 p-4 sm:px-6 lg:grid-cols-4">
			<StatCard label="Active" :value="active.length" />
			<StatCard label="Paid so far" :value="fmt(sum(active, 'paid_amount'))" />
			<StatCard label="Still to pay" :value="fmt(sum(active, 'remaining'))" />
			<StatCard label="Due now" :value="dueNow" :tone="dueNow ? 'amber' : undefined" hint="Posted by the daily job" />
		</div>

		<div class="flex flex-wrap gap-2 px-4 pb-2 sm:px-6">
			<div class="max-w-full overflow-x-auto"><TabButtons v-model="view" :options="VIEWS.map((v) => ({ label: v, value: v }))" /></div>
			<div class="w-full sm:ml-auto sm:w-64">
				<TextInput v-model="query" type="search" placeholder="Search title, payee or project" :debounce="150">
					<template #prefix><span class="lucide-search size-4 text-ink-gray-5" aria-hidden="true" /></template>
				</TextInput>
			</div>
		</div>
		<FilterBar v-model="filters" :fields="FILTERS" />

		<DataTable :columns="columns" :rows="filtered" :loading="loading" clickable empty-text="No recurring payments" @row-click="(r) => $router.push(`/recurring/${r.name}`)">
			<template #title="{ row }">
				<div class="font-medium text-ink-gray-9">{{ row.title }}</div>
				<div class="text-sm text-ink-gray-5">{{ [row.name, row.payee, row.project].filter(Boolean).join(" · ") }}</div>
			</template>
			<template #frequency="{ row }">
				<div>{{ row.frequency }}</div>
				<div class="text-sm text-ink-gray-5">{{ date(row.from_date) }} – {{ date(row.to_date) }}</div>
			</template>
			<template #next_date="{ row }">
				<template v-if="row.next_date && row.status !== 'Cancelled'">
					<div :class="row.next_date <= today() && row.status === 'Active' ? 'text-ink-amber-3' : ''">{{ date(row.next_date) }}</div>
					<div class="text-sm text-ink-gray-5">{{ fmt(row.next_amount) }}</div>
				</template>
				<span v-else class="text-ink-gray-5">—</span>
			</template>
			<template #paid_amount="{ row }">
				<div class="w-40"><UsageBar :value="row.total_amount ? (row.paid_amount / row.total_amount) * 100 : 0" :caption="`${fmt(row.paid_amount)} / ${fmt(row.total_amount)}`" /></div>
			</template>
			<template #status="{ value }"><StatusBadge :status="value" /></template>
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
import { date, money, today } from "@/format"
import { can, currency, session } from "@/store"

const VIEWS = ["Active", "Draft", "Stopped", "Completed", "All"]

const FILTERS: FilterField[] = [
	{ key: "period", label: "Paying", type: "date-range", match: overlaps("from_date", "to_date") },
	{ key: "project", label: "Project", type: "link", doctype: "Project", filters: { company: session.company } },
	{ key: "cost_center", label: "Cost center", type: "link", doctype: "Cost Center", filters: { company: session.company, is_group: 0 } },
	{ key: "expense_account", label: "Expense account", type: "link", doctype: "Account", filters: { company: session.company, is_group: 0, root_type: "Expense" } },
]

const filters = useListFilters(FILTERS)
const rows = ref<any[]>([])
const loading = ref(true)
const view = ref("Active")
const query = ref("")
const fmt = (v: number) => money(v, currency.value)

const columns: Column[] = [
	{ key: "title", label: "Payment" },
	{ key: "expense_account", label: "Expense Account" },
	{ key: "frequency", label: "Frequency" },
	{ key: "next_date", label: "Next" },
	{ key: "paid_amount", label: "Paid" },
	{ key: "status", label: "Status" },
]

const active = computed(() => rows.value.filter((r) => r.status === "Active"))
const dueNow = computed(() => active.value.filter((r) => r.next_date && r.next_date <= today()).length)
const filtered = computed(() => {
	const q = query.value.trim().toLowerCase()
	return rows.value.filter(
		(r) =>
			(view.value === "All" || r.status === view.value) &&
			matchRow(FILTERS, filters, r) &&
			(!q || `${r.title} ${r.name} ${r.payee || ""} ${r.project || ""}`.toLowerCase().includes(q)),
	)
})

function sum(list: any[], field: string) {
	return list.reduce((total, r) => total + Number(r[field] || 0), 0)
}

onMounted(async () => {
	try {
		rows.value = await api("spend.api.get_recurring_payments", { company: session.company })
	} finally {
		loading.value = false
	}
})
</script>
