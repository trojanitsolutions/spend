<template>
	<Dialog v-model:open="open" title="New item" :actions="[{ label: 'Create', variant: 'solid', loading: saving, onClick: create }]">
		<form class="space-y-4" @submit.prevent="create">
			<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
				<FormControl v-model="draft.item_code" label="Item code" required placeholder="e.g. CEMENT-OPC53" />
				<FormControl v-model="draft.item_name" label="Item name" placeholder="Same as the code when empty" />
				<LinkField v-model="draft.item_group" doctype="Item Group" label="Item group" required />
				<div class="flex items-end gap-1">
					<LinkField v-model="draft.stock_uom" class="min-w-0 flex-1" doctype="UOM" label="Default unit of measure" required :filters="{ enabled: 1 }" />
					<Button v-if="can('UOM', 'create')" variant="ghost" icon="lucide-plus" aria-label="New unit" title="New unit" @click="uomOpen = true" />
				</div>
				<FormControl v-model="draft.standard_rate" type="number" min="0" step="0.01" label="Standard buying rate" />
				<FormControl v-model="draft.is_fixed_asset" class="self-end" type="checkbox" label="Is fixed asset" />
			</div>
			<p class="text-sm text-ink-gray-5">More units of measure, the description and asset options are on the item page.</p>
		</form>
		<UomDialog v-model:open="uomOpen" @created="(u) => (draft.stock_uom = u)" />
	</Dialog>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from "vue"
import { Button, Dialog, FormControl, toast } from "frappe-ui"
import LinkField from "@/components/LinkField.vue"
import UomDialog from "@/components/UomDialog.vue"
import { insertDoc } from "@/api"
import { can } from "@/store"

// ERPNext-style quick entry; the full form is pages/ItemForm.vue
const emit = defineEmits<{ saved: [name: string] }>()
const open = defineModel<boolean>("open", { default: false })

const saving = ref(false)
const uomOpen = ref(false)
const blank = () => ({ item_code: "", item_name: "", item_group: "All Item Groups", stock_uom: "Nos", standard_rate: "" as number | string, is_fixed_asset: false })
const draft = reactive(blank())

watch(open, (value) => value && Object.assign(draft, blank()))

async function create() {
	const code = draft.item_code.trim()
	if (!code || !draft.item_group || !draft.stock_uom) {
		toast.error("Enter an item code, item group and unit of measure")
		return
	}
	saving.value = true
	try {
		const saved = await insertDoc<{ name: string }>({
			doctype: "Item",
			item_code: code,
			item_name: draft.item_name.trim() || code,
			item_group: draft.item_group,
			stock_uom: draft.stock_uom,
			standard_rate: Number(draft.standard_rate) || 0,
			is_fixed_asset: draft.is_fixed_asset ? 1 : 0,
		})
		toast.success(`${saved.name} created`)
		emit("saved", saved.name)
		open.value = false
	} finally {
		saving.value = false
	}
}
</script>
