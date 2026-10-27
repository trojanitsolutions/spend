<template>
	<div>
		<PageHeader title="Expense Categories" subtitle="Tag project spend by category and sub category">
			<template #actions>
				<Button icon-left="lucide-chart-column" label="Monthly report" @click="$router.push('/reports/project-category-monthly')" />
				<template v-if="can('Expense Category', 'create')">
					<Button icon-left="lucide-plus" label="New Sub Category" :disabled="!parents.length" @click="openNew(parents[0]?.name)" />
					<Button variant="solid" icon-left="lucide-plus" label="New Category" @click="openNew()" />
				</template>
			</template>
		</PageHeader>
		<TreeTable
			class="mt-2"
			:rows="rows"
			:loading="loading"
			name-field="name"
			name-label="Category"
			parent-field="parent_category"
			:collapsed="collapsed"
			:label="(r) => r.category_name"
			:columns="[
				{ key: 'expense_account', label: 'Expense account', format: (v: string, r: any) => v || (r.parent_category ? 'From the category' : '—') },
				{ key: 'disabled', label: 'Status', format: (v: number) => (v ? 'Disabled' : 'Active') },
			]"
			:clickable="can('Expense Category', 'write')"
			@row-click="openEdit"
			@toggle="toggle"
		/>
		<EmptyState v-if="!loading && !rows.length" icon="lucide-tags" title="No categories yet" message="Create a parent category, then its sub categories." />

		<Dialog v-model:open="dialogOpen" :title="dialogTitle" :actions="dialogActions">
			<form class="space-y-4" @submit.prevent="save">
				<FormControl v-model="draft.category_name" label="Name" required placeholder="e.g. Materials or Cement" :disabled="!!draft.name" />
				<FormControl v-model="draft.is_parent_category" type="checkbox" label="Parent category (holds sub categories)" :disabled="hasSubs" />
				<LinkField
					v-if="!draft.is_parent_category"
					v-model="draft.parent_category"
					doctype="Expense Category"
					label="Parent category"
					required
					:filters="{ company: session.company, is_parent_category: 1, disabled: 0 }"
				/>
				<LinkField
					v-model="draft.expense_account"
					doctype="Account"
					label="Expense account"
					:description="draft.is_parent_category ? 'Filled in on bookings that pick this category' : 'Leave empty to use the parent category\'s account'"
					:filters="{ company: session.company, is_group: 0, disabled: 0, root_type: 'Expense' }"
				/>
				<FormControl v-if="draft.name" v-model="draft.disabled" type="checkbox" label="Disabled" />
			</form>
		</Dialog>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue"
import { Button, Dialog, FormControl, toast } from "frappe-ui"
import EmptyState from "@/components/EmptyState.vue"
import LinkField from "@/components/LinkField.vue"
import PageHeader from "@/components/PageHeader.vue"
import TreeTable from "@/components/TreeTable.vue"
import { api, getList, insertDoc } from "@/api"
import { can, session } from "@/store"

interface Category {
	name: string
	category_name: string
	is_parent_category: 0 | 1
	parent_category: string | null
	expense_account: string | null
	disabled: 0 | 1
}

const categories = ref<Category[]>([])
const loading = ref(false)
const collapsed = ref(new Set<string>())
const dialogOpen = ref(false)
const draft = reactive({ name: "", category_name: "", is_parent_category: true, parent_category: "", expense_account: "", disabled: false })

// each parent followed by its sub categories
const rows = computed(() => {
	const subs = (parent: string) => categories.value.filter((c) => c.parent_category === parent).map((c) => ({ ...c, indent: 1 }))
	return categories.value.filter((c) => !c.parent_category).flatMap((c) => [{ ...c, is_group: c.is_parent_category, indent: 0 }, ...subs(c.name)])
})
const parents = computed(() => categories.value.filter((c) => c.is_parent_category && !c.disabled))
const dialogTitle = computed(() => (draft.name ? `Edit ${draft.category_name}` : draft.is_parent_category ? "New expense category" : "New sub category"))
// a saved parent category can get a sub category straight from its dialog
const dialogActions = computed(() => [
	...(draft.name && draft.is_parent_category && can("Expense Category", "create") ? [{ label: "Add Sub Category", onClick: () => openNew(draft.name) }] : []),
	{ label: draft.name ? "Save" : "Create", variant: "solid", onClick: save },
])
const hasSubs = computed(() => !!draft.name && categories.value.some((c) => c.parent_category === draft.name))

function toggle(name: string) {
	const next = new Set(collapsed.value)
	next.has(name) ? next.delete(name) : next.add(name)
	collapsed.value = next
}

// with `parent` the new category is one of its sub categories
function openNew(parent?: string) {
	Object.assign(draft, { name: "", category_name: "", is_parent_category: !parent, parent_category: parent || "", expense_account: "", disabled: false })
	dialogOpen.value = true
}

function openEdit(row: Category) {
	Object.assign(draft, {
		name: row.name,
		category_name: row.category_name,
		is_parent_category: !!row.is_parent_category,
		parent_category: row.parent_category || "",
		expense_account: row.expense_account || "",
		disabled: !!row.disabled,
	})
	dialogOpen.value = true
}

async function save() {
	if (!draft.category_name.trim()) {
		toast.error("Enter a name")
		return
	}
	const values = {
		is_parent_category: draft.is_parent_category ? 1 : 0,
		parent_category: draft.is_parent_category ? null : draft.parent_category,
		expense_account: draft.expense_account || null,
		disabled: draft.disabled ? 1 : 0,
	}
	if (draft.name) {
		await api("frappe.client.set_value", { doctype: "Expense Category", name: draft.name, fieldname: values })
		toast.success("Category saved")
	} else {
		const saved = await insertDoc<{ name: string }>({ doctype: "Expense Category", company: session.company, category_name: draft.category_name.trim(), ...values })
		toast.success(`${saved.name} created`)
	}
	dialogOpen.value = false
	await load()
}

async function load() {
	loading.value = true
	try {
		categories.value = await getList<Category>(
			"Expense Category",
			["name", "category_name", "is_parent_category", "parent_category", "expense_account", "disabled"],
			{ company: session.company },
			"category_name asc",
			0,
		)
	} finally {
		loading.value = false
	}
}

onMounted(load)
watch(() => session.company, load)
</script>
