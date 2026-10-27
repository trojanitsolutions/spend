<template>
	<div>
		<PageHeader title="Items" subtitle="The goods and services you buy. Pick them on bill lines.">
			<template #actions>
				<Button icon-left="lucide-folder-tree" label="Item Groups" @click="$router.push('/item-groups')" />
				<Button v-if="can('Item', 'create')" variant="solid" icon-left="lucide-plus" label="New Item" @click="$router.push('/items/new')" />
			</template>
		</PageHeader>

		<div class="flex flex-wrap items-end gap-2 p-4 pb-2 sm:px-6">
			<TabButtons v-model="view" :options="VIEWS.map((v) => ({ label: v, value: v }))" />
			<div class="w-full sm:ml-auto sm:w-56">
				<LinkField v-model="group" doctype="Item Group" placeholder="All item groups" />
			</div>
			<div class="w-full sm:w-56">
				<TextInput v-model="query" type="search" placeholder="Search items" :debounce="150">
					<template #prefix><span class="lucide-search size-4 text-ink-gray-5" aria-hidden="true" /></template>
				</TextInput>
			</div>
		</div>

		<EmptyState v-if="!loading && !rows.length && !group" icon="lucide-package" title="Add your first item" message="Items are the goods and services you buy. Pick them on bill lines.">
			<Button v-if="can('Item', 'create')" variant="solid" icon-left="lucide-plus" label="New Item" @click="$router.push('/items/new')" />
		</EmptyState>
		<DataTable v-else :columns="columns" :rows="filtered" :loading="loading" clickable empty-text="No items match" @row-click="(r) => $router.push(`/items/${encodeURIComponent(r.name)}`)">
			<template #name="{ row }">
				<div class="font-medium text-ink-gray-9">
					{{ row.item_name }}<Badge v-if="row.is_fixed_asset" class="ml-2" theme="blue" label="Fixed asset" />
				</div>
				<div v-if="row.item_name !== row.name" class="text-sm text-ink-gray-5">{{ row.name }}</div>
			</template>
		</DataTable>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { Badge, Button, TabButtons, TextInput } from "frappe-ui"
import DataTable, { type Column } from "@/components/DataTable.vue"
import EmptyState from "@/components/EmptyState.vue"
import LinkField from "@/components/LinkField.vue"
import PageHeader from "@/components/PageHeader.vue"
import { getList } from "@/api"
import { money } from "@/format"
import { can, currency } from "@/store"

const VIEWS = ["Active", "Fixed assets", "Disabled", "All"]

interface Item {
	name: string
	item_name: string
	item_group: string
	stock_uom: string
	standard_rate: number
	last_purchase_rate: number
	is_fixed_asset: 0 | 1
	disabled: 0 | 1
}

const rows = ref<Item[]>([])
const loading = ref(true)
const view = ref("Active")
const query = ref("")
const group = ref("")

const columns: Column[] = [
	{ key: "name", label: "Item" },
	{ key: "item_group", label: "Item group" },
	{ key: "stock_uom", label: "UOM" },
	{ key: "standard_rate", label: "Standard rate", align: "right", format: (v) => (v ? money(v, currency.value) : "—") },
	{ key: "last_purchase_rate", label: "Last purchase rate", align: "right", format: (v) => (v ? money(v, currency.value) : "—") },
	{ key: "disabled", label: "Status", format: (v) => (v ? "Disabled" : "Active") },
]

const filtered = computed(() => {
	const q = query.value.trim().toLowerCase()
	return rows.value.filter(
		(r) =>
			(view.value === "All" || (view.value === "Fixed assets" ? !r.disabled && r.is_fixed_asset : !!r.disabled === (view.value === "Disabled"))) &&
			(!q || `${r.name} ${r.item_name}`.toLowerCase().includes(q)),
	)
})

async function load() {
	loading.value = true
	try {
		// a group shows its sub groups' items too
		const filters = group.value ? [["item_group", "descendants of (inclusive)", group.value]] : {}
		rows.value = await getList<Item>("Item", ["name", "item_name", "item_group", "stock_uom", "standard_rate", "last_purchase_rate", "is_fixed_asset", "disabled"], filters, "item_name asc", 0)
	} finally {
		loading.value = false
	}
}

onMounted(load)
watch(group, load)
</script>
