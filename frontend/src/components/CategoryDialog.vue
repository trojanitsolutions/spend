<template>
	<Dialog v-model:open="open" :title="parent ? `New sub category of ${parent}` : 'New expense category'" :actions="[{ label: 'Create', variant: 'solid', loading: saving, onClick: create }]">
		<form class="space-y-4" @submit.prevent="create">
			<FormControl v-model="draft.category_name" label="Name" required :placeholder="parent ? 'e.g. Cement' : 'e.g. Materials'" />
			<LinkField
				v-model="draft.expense_account"
				doctype="Account"
				label="Expense account"
				:description="parent ? 'Leave empty to use the account of the category' : 'Filled in on bookings that pick this category'"
				:filters="{ company: session.company, is_group: 0, disabled: 0, root_type: 'Expense' }"
			/>
		</form>
	</Dialog>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from "vue"
import { Dialog, FormControl, toast } from "frappe-ui"
import LinkField from "@/components/LinkField.vue"
import { insertDoc } from "@/api"
import { session } from "@/store"

// without `parent` it creates a parent category, with it a sub category of `parent`
const props = defineProps<{ parent?: string }>()
const emit = defineEmits<{ created: [name: string] }>()
const open = defineModel<boolean>("open", { default: false })

const saving = ref(false)
const draft = reactive({ category_name: "", expense_account: "" })

watch(open, (value) => value && Object.assign(draft, { category_name: "", expense_account: "" }))

async function create() {
	if (!draft.category_name.trim()) {
		toast.error("Enter a name")
		return
	}
	saving.value = true
	try {
		const saved = await insertDoc<{ name: string }>({
			doctype: "Expense Category",
			company: session.company,
			category_name: draft.category_name.trim(),
			is_parent_category: props.parent ? 0 : 1,
			parent_category: props.parent || undefined,
			expense_account: draft.expense_account || undefined,
		})
		toast.success(`${saved.name} created`)
		emit("created", saved.name)
		open.value = false
	} finally {
		saving.value = false
	}
}
</script>
