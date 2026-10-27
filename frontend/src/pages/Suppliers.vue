<template>
	<div>
		<PageHeader title="Suppliers" subtitle="Who you buy from and what you owe them">
			<template #actions>
				<Button icon-left="lucide-chart-column" label="Supplier Outstanding" @click="$router.push('/reports/supplier-outstanding')" />
				<Button v-if="can('Supplier', 'create')" variant="solid" icon-left="lucide-plus" label="New Supplier" @click="openNew" />
			</template>
		</PageHeader>

		<div class="grid grid-cols-2 gap-3 p-4 sm:grid-cols-3 sm:px-6">
			<StatCard label="Suppliers" :value="rows.filter((r) => !r.disabled).length" />
			<StatCard label="Outstanding" :value="fmt(sum('outstanding'))" />
			<StatCard label="Overdue" :value="fmt(sum('overdue'))" :tone="sum('overdue') > 0 ? 'red' : undefined" />
		</div>

		<div class="flex flex-wrap gap-2 px-4 pb-2 sm:px-6">
			<div class="max-w-full overflow-x-auto"><TabButtons v-model="view" :options="VIEWS.map((v) => ({ label: v, value: v }))" /></div>
			<div class="w-full sm:ml-auto sm:w-64">
				<TextInput v-model="query" type="search" placeholder="Search suppliers" :debounce="150">
					<template #prefix><span class="lucide-search size-4 text-ink-gray-5" aria-hidden="true" /></template>
				</TextInput>
			</div>
		</div>

		<DataTable :columns="columns" :rows="filtered" :loading="loading" clickable empty-text="No suppliers match" @row-click="(r) => $router.push(`/suppliers/${encodeURIComponent(r.name)}`)">
			<template #supplier_name="{ row }">
				<div class="font-medium text-ink-gray-9">{{ row.supplier_name }}</div>
				<div v-if="row.tax_id" class="text-sm text-ink-gray-5">Tax ID {{ row.tax_id }}</div>
			</template>
			<template #contact="{ row }">
				<div class="text-ink-gray-7">{{ row.email || "—" }}</div>
				<div v-if="row.phone" class="text-sm text-ink-gray-5">{{ row.phone }}</div>
			</template>
			<template #overdue="{ value }">
				<span :class="value > 0 ? 'text-ink-red-4' : 'text-ink-gray-5'">{{ value > 0 ? fmt(value) : "—" }}</span>
			</template>
		</DataTable>

		<Dialog v-model:open="dialogOpen" title="New supplier" :actions="[{ label: 'Create', variant: 'solid', onClick: create }]">
			<form class="space-y-4" @submit.prevent="create">
				<FormControl v-model="draft.supplier_name" label="Supplier name" required placeholder="e.g. Acme Office Supplies" />
				<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
					<FormControl v-model="draft.tax_id" label="Tax ID" />
					<FormControl v-model="draft.phone" label="Phone" />
				</div>
				<FormControl v-model="draft.email" type="email" label="Email" />
				<FormControl v-model="draft.address" type="textarea" label="Address" />
			</form>
		</Dialog>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue"
import { useRouter } from "vue-router"
import { Button, Dialog, FormControl, TabButtons, TextInput, toast } from "frappe-ui"
import DataTable, { type Column } from "@/components/DataTable.vue"
import PageHeader from "@/components/PageHeader.vue"
import StatCard from "@/components/StatCard.vue"
import { api, insertDoc } from "@/api"
import { money } from "@/format"
import { can, currency, session } from "@/store"

const VIEWS = ["All", "Owed", "Overdue"]

const router = useRouter()
const rows = ref<any[]>([])
const loading = ref(true)
const view = ref("All")
const query = ref("")
const dialogOpen = ref(false)
const draft = reactive({ supplier_name: "", tax_id: "", email: "", phone: "", address: "" })
const fmt = (v: number) => money(v, currency.value)

const columns: Column[] = [
	{ key: "supplier_name", label: "Supplier" },
	{ key: "contact", label: "Contact" },
	{ key: "open_bills", label: "Open Bills", align: "right", format: (v) => (v ? String(v) : "—") },
	{ key: "overdue", label: "Overdue", align: "right" },
	{ key: "outstanding", label: "Outstanding", align: "right", format: (v) => fmt(v) },
]

const filtered = computed(() => {
	const q = query.value.trim().toLowerCase()
	return rows.value.filter(
		(r) =>
			(view.value === "All" || (view.value === "Owed" ? r.outstanding > 0 : r.overdue > 0)) &&
			(!q || `${r.supplier_name} ${r.tax_id || ""} ${r.email || ""}`.toLowerCase().includes(q)),
	)
})

function sum(field: string) {
	return rows.value.reduce((total, r) => total + Number(r[field] || 0), 0)
}

function openNew() {
	Object.assign(draft, { supplier_name: "", tax_id: "", email: "", phone: "", address: "" })
	dialogOpen.value = true
}

async function create() {
	if (!draft.supplier_name.trim()) {
		toast.error("Enter a supplier name")
		return
	}
	const saved = await insertDoc<{ name: string }>({ doctype: "Supplier", ...draft })
	dialogOpen.value = false
	toast.success(`Supplier ${saved.name} created`)
	router.push(`/suppliers/${encodeURIComponent(saved.name)}`)
}

onMounted(async () => {
	try {
		rows.value = await api("spend.api.get_suppliers", { company: session.company })
	} finally {
		loading.value = false
	}
})
</script>
