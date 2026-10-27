<template>
	<div>
		<PageHeader title="Item Groups" subtitle="Group items in a tree. A group's defaults apply to its items and to its sub groups." :back="{ to: '/items', label: 'Items' }">
			<template #actions>
				<Button v-if="can('Item Group', 'create')" variant="solid" icon-left="lucide-plus" label="New Item Group" @click="openNew(ROOT)" />
			</template>
		</PageHeader>
		<TreeTable
			class="mt-2"
			:rows="rows"
			:loading="loading"
			name-field="name"
			name-label="Item group"
			parent-field="parent_item_group"
			:collapsed="collapsed"
			:columns="[
				{ key: 'expense_account', label: 'Default expense account', format: (v: string) => v || '—' },
				{ key: 'buying_cost_center', label: 'Default cost center', format: (v: string) => v || '—' },
				{ key: 'items', label: 'Items', align: 'right' },
			]"
			:clickable="can('Item Group', 'write')"
			@row-click="openEdit"
			@toggle="toggle"
		/>

		<Dialog v-model:open="dialogOpen" :title="draft.name ? `Edit ${draft.name}` : 'New item group'" :actions="dialogActions">
			<form class="space-y-4" @submit.prevent="save">
				<FormControl v-model="draft.item_group_name" label="Name" required placeholder="e.g. Building Materials" :disabled="!!draft.name" />
				<LinkField
					v-if="draft.name !== ROOT"
					v-model="draft.parent_item_group"
					doctype="Item Group"
					label="Parent item group"
					required
					:filters="{ is_group: 1, name: ['!=', draft.name || ''] }"
				/>
				<FormControl v-model="draft.is_group" type="checkbox" label="Group (holds other item groups)" :disabled="hasChildren" />
				<div class="space-y-3 rounded-lg border border-outline-gray-1 p-3">
					<div class="text-sm font-medium text-ink-gray-7">Defaults for {{ session.company }}</div>
					<LinkField
						v-model="draft.expense_account"
						doctype="Account"
						label="Default expense account"
						description="Empty uses the parent group's, then the company's"
						:filters="{ company: session.company, is_group: 0, disabled: 0, root_type: 'Expense' }"
					/>
					<LinkField v-model="draft.buying_cost_center" doctype="Cost Center" label="Default buying cost center" :filters="{ company: session.company, is_group: 0, disabled: 0 }" />
				</div>
			</form>
		</Dialog>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue"
import { Button, Dialog, FormControl, toast } from "frappe-ui"
import LinkField from "@/components/LinkField.vue"
import PageHeader from "@/components/PageHeader.vue"
import TreeTable from "@/components/TreeTable.vue"
import { api, getDoc, insertDoc } from "@/api"
import { can, session } from "@/store"

const ROOT = "All Item Groups"

interface Group {
	name: string
	parent_item_group: string | null
	is_group: 0 | 1
	lft: number
	rgt: number
	expense_account: string | null
	buying_cost_center: string | null
	items: number
}

const groups = ref<Group[]>([])
const loading = ref(false)
const collapsed = ref(new Set<string>())
const dialogOpen = ref(false)
const draft = reactive({ name: "", item_group_name: "", parent_item_group: ROOT, is_group: false, expense_account: "", buying_cost_center: "" })

// in tree order, each row indented by its depth
const rows = computed(() => {
	const open: Group[] = []
	return groups.value.map((g) => {
		while (open.length && open[open.length - 1].rgt < g.lft) open.pop()
		const row = { ...g, indent: open.length }
		open.push(g)
		return row
	})
})
const hasChildren = computed(() => !!draft.name && groups.value.some((g) => g.parent_item_group === draft.name))
const dialogActions = computed(() => [
	...(draft.name && draft.is_group && can("Item Group", "create") ? [{ label: "Add Sub Group", onClick: () => openNew(draft.name) }] : []),
	{ label: draft.name ? "Save" : "Create", variant: "solid", onClick: save },
])

function toggle(name: string) {
	const next = new Set(collapsed.value)
	next.has(name) ? next.delete(name) : next.add(name)
	collapsed.value = next
}

function openNew(parent: string) {
	Object.assign(draft, { name: "", item_group_name: "", parent_item_group: parent, is_group: false, expense_account: "", buying_cost_center: "" })
	dialogOpen.value = true
}

function openEdit(row: Group) {
	Object.assign(draft, {
		name: row.name,
		item_group_name: row.name,
		parent_item_group: row.parent_item_group || "",
		is_group: !!row.is_group,
		expense_account: row.expense_account || "",
		buying_cost_center: row.buying_cost_center || "",
	})
	dialogOpen.value = true
}

async function save() {
	if (!draft.item_group_name.trim()) {
		toast.error("Enter a name")
		return
	}
	const values = { parent_item_group: draft.name === ROOT ? "" : draft.parent_item_group, is_group: draft.is_group ? 1 : 0 }
	const row = { company: session.company, expense_account: draft.expense_account || null, buying_cost_center: draft.buying_cost_center || null }
	const keep = row.expense_account || row.buying_cost_center
	if (draft.name) {
		// other companies' rows stay as they are
		const doc = await getDoc<any>("Item Group", draft.name)
		const others = doc.item_group_defaults.filter((d: any) => d.company !== session.company)
		await api("frappe.client.save", { doc: { ...doc, ...values, item_group_defaults: keep ? [...others, row] : others } })
		toast.success("Item group saved")
	} else {
		const saved = await insertDoc<{ name: string }>({ doctype: "Item Group", item_group_name: draft.item_group_name.trim(), ...values, item_group_defaults: keep ? [row] : [] })
		toast.success(`${saved.name} created`)
	}
	dialogOpen.value = false
	await load()
}

async function load() {
	loading.value = true
	try {
		groups.value = await api("spend.api.get_item_groups", { company: session.company })
	} finally {
		loading.value = false
	}
}

onMounted(load)
watch(() => session.company, load)
</script>
