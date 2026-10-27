<template>
	<Dialog v-model:open="open" title="New unit" :actions="[{ label: 'Create', variant: 'solid', loading: saving, onClick: create }]">
		<form class="space-y-4" @submit.prevent="create">
			<FormControl v-model="draft.uom_name" label="Name" required placeholder="e.g. Roll" />
			<FormControl v-model="draft.must_be_whole_number" type="checkbox" label="Must be whole number" />
		</form>
	</Dialog>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from "vue"
import { Dialog, FormControl, toast } from "frappe-ui"
import { insertDoc } from "@/api"

const emit = defineEmits<{ created: [name: string] }>()
const open = defineModel<boolean>("open", { default: false })

const saving = ref(false)
const draft = reactive({ uom_name: "", must_be_whole_number: false })

watch(open, (value) => value && Object.assign(draft, { uom_name: "", must_be_whole_number: false }))

async function create() {
	if (!draft.uom_name.trim()) {
		toast.error("Enter a name")
		return
	}
	saving.value = true
	try {
		const saved = await insertDoc<{ name: string }>({ doctype: "UOM", uom_name: draft.uom_name.trim(), must_be_whole_number: draft.must_be_whole_number ? 1 : 0 })
		toast.success(`${saved.name} created`)
		emit("created", saved.name)
		open.value = false
	} finally {
		saving.value = false
	}
}
</script>
