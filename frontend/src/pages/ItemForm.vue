<template>
	<div v-if="loading" class="p-6"><LoadingText /></div>
	<div v-else>
		<PageHeader :title="doc ? doc.item_name : 'New Item'" :subtitle="subtitle" :back="{ to: '/items', label: 'Items' }">
			<template v-if="doc" #badge><Badge :theme="doc.disabled ? 'gray' : 'green'" :label="doc.disabled ? 'Disabled' : 'Enabled'" /></template>
			<template #actions>
				<template v-if="doc">
					<Button label="Open in Desk" icon-left="lucide-external-link" @click="openDesk" />
					<Button v-if="can('Item', 'delete')" theme="red" label="Delete" @click="remove" />
				</template>
				<Button v-if="canWrite" variant="solid" :label="doc ? 'Save' : 'Create Item'" :loading="saving" @click="save" />
			</template>
		</PageHeader>

		<form class="mx-auto max-w-3xl space-y-6 p-4 sm:p-6" @submit.prevent="save">
			<fieldset class="grid grid-cols-1 gap-4 rounded-xl border border-outline-gray-1 p-4 sm:grid-cols-2" :disabled="!canWrite">
				<legend class="px-1 text-base font-semibold">Item</legend>
				<FormControl v-model="draft.item_code" label="Item code" required placeholder="e.g. CEMENT-OPC53" :disabled="!!doc" />
				<FormControl v-model="draft.item_name" label="Item name" placeholder="Same as the code when empty" />
				<div class="flex items-end gap-1">
					<LinkField v-model="draft.item_group" class="min-w-0 flex-1" doctype="Item Group" label="Item group" required />
					<Button variant="ghost" icon="lucide-folder-tree" aria-label="Item groups" title="Item groups" @click="$router.push('/item-groups')" />
				</div>
				<div class="flex items-end gap-1">
					<LinkField v-model="draft.stock_uom" class="min-w-0 flex-1" doctype="UOM" label="Default unit of measure" required :filters="{ enabled: 1 }" />
					<Button v-if="can('UOM', 'create')" variant="ghost" icon="lucide-plus" aria-label="New unit" title="New unit" @click="uomFor = (u) => (draft.stock_uom = u)" />
				</div>
				<div class="flex flex-col gap-2 sm:col-span-2 sm:flex-row sm:gap-6">
					<FormControl v-model="draft.disabled" type="checkbox" label="Disabled" />
				</div>
			</fieldset>

			<fieldset class="grid grid-cols-1 gap-4 rounded-xl border border-outline-gray-1 p-4 sm:grid-cols-2" :disabled="!canWrite">
				<legend class="px-1 text-base font-semibold">Purchasing</legend>
				<FormControl v-model="draft.standard_rate" type="number" min="0" step="0.01" :label="`Standard buying rate (per ${draft.stock_uom || 'unit'})`" description="Used until a supplier bills this item" />
				<FormControl :model-value="doc?.last_purchase_rate ? fmt(doc.last_purchase_rate) : '—'" label="Last purchase rate" description="From the last submitted bill" disabled />
				<FormControl v-model="draft.is_fixed_asset" type="checkbox" label="Is fixed asset" :disabled="lockedAsset" :description="lockedAsset ? 'Submitted bills use this item' : 'Bills book it to an asset account, not an expense'" />
				<FormControl v-if="draft.is_fixed_asset" v-model="draft.auto_create_assets" type="checkbox" label="Auto create assets on purchase" description="One draft asset per unit when a bill is submitted" />
			</fieldset>

			<fieldset class="space-y-4 rounded-xl border border-outline-gray-1 p-4" :disabled="!canWrite">
				<legend class="px-1 text-base font-semibold">Units of measure</legend>
				<LinkField
					v-model="draft.purchase_uom"
					doctype="UOM"
					label="Default purchase unit of measure"
					:placeholder="draft.stock_uom || 'Same as the default unit'"
					description="Filled in on bills. It must be in the table below."
					:filters="{ enabled: 1 }"
				/>
				<div>
					<div class="mb-1.5 grid grid-cols-[1fr_10rem_auto] gap-2 text-xs text-ink-gray-5">
						<span>UOM</span>
						<span>{{ draft.stock_uom || "Default units" }} in one</span>
						<span class="w-7" />
					</div>
					<div v-for="(row, i) in draft.uoms" :key="row.key" class="mb-2 grid grid-cols-[1fr_10rem_auto] items-center gap-2">
						<div class="flex items-center gap-1">
							<LinkField v-model="row.uom" class="min-w-0 flex-1" doctype="UOM" placeholder="e.g. Box" :filters="{ enabled: 1 }" />
							<Button v-if="can('UOM', 'create')" variant="ghost" icon="lucide-plus" aria-label="New unit" title="New unit" @click="uomFor = (u) => (row.uom = u)" />
						</div>
						<FormControl v-model="row.conversion_factor" type="number" min="0" step="any" :disabled="row.uom === draft.stock_uom" />
						<Button variant="ghost" icon="lucide-trash-2" :aria-label="`Remove UOM ${i + 1}`" :disabled="row.uom === draft.stock_uom" @click="draft.uoms.splice(i, 1)" />
					</div>
					<Button icon-left="lucide-plus" label="Add UOM" @click="draft.uoms.push(uomRow())" />
				</div>
			</fieldset>

			<fieldset class="rounded-xl border border-outline-gray-1 p-4" :disabled="!canWrite">
				<legend class="px-1 text-base font-semibold">Description</legend>
				<FormControl v-model="draft.description" type="textarea" :rows="4" placeholder="Filled in on bill lines" />
			</fieldset>
		</form>
		<UomDialog :open="!!uomFor" @update:open="(v) => !v && (uomFor = null)" @created="(u) => uomFor?.(u)" />
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { Badge, Button, FormControl, LoadingText, dialog, toast } from "frappe-ui"
import LinkField from "@/components/LinkField.vue"
import PageHeader from "@/components/PageHeader.vue"
import UomDialog from "@/components/UomDialog.vue"
import { api, getDoc, insertDoc } from "@/api"
import { money } from "@/format"
import { can, currency } from "@/store"

// without `name` it is a new item
const props = defineProps<{ name?: string }>()

const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const doc = ref<any>(null)
const lockedAsset = ref(false)
// fills the unit field that asked for a new unit
const uomFor = ref<((uom: string) => void) | null>(null)
const fmt = (v: number) => money(v, currency.value)
let nextKey = 1

const uomRow = (uom = "", conversion_factor: number | string = "") => ({ key: nextKey++, uom, conversion_factor })
const blank = () => ({
	item_code: "",
	item_name: "",
	item_group: "All Item Groups",
	stock_uom: "Nos",
	disabled: false,
	standard_rate: "" as number | string,
	is_fixed_asset: false,
	auto_create_assets: false,
	purchase_uom: "",
	description: "",
	uoms: [] as ReturnType<typeof uomRow>[],
})
const draft = reactive(blank())

const canWrite = computed(() => can("Item", doc.value ? "write" : "create"))
const subtitle = computed(() => (doc.value ? [doc.value.name, doc.value.item_group, doc.value.is_fixed_asset && "Fixed asset"].filter(Boolean).join(" · ") : "Something you buy"))

async function load() {
	doc.value = null
	Object.assign(draft, blank())
	if (!props.name) return
	loading.value = true
	try {
		const d = await getDoc<any>("Item", props.name)
		doc.value = d
		Object.assign(draft, {
			item_code: d.name,
			item_name: d.item_name,
			item_group: d.item_group,
			stock_uom: d.stock_uom,
			disabled: !!d.disabled,
			standard_rate: d.standard_rate || "",
			is_fixed_asset: !!d.is_fixed_asset,
			auto_create_assets: !!d.auto_create_assets,
			purchase_uom: d.purchase_uom || "",
			description: d.description || "",
			uoms: d.uoms.map((r: any) => uomRow(r.uom, r.conversion_factor)),
		})
		lockedAsset.value = !!(await api("frappe.client.get_count", { doctype: "Purchase Invoice", filters: [["Purchase Invoice Item", "item_code", "=", d.name], ["docstatus", "=", 1]] }, { silent: true }).catch(() => 0))
	} finally {
		loading.value = false
	}
}

async function save() {
	const code = draft.item_code.trim()
	if (!code || !draft.item_group || !draft.stock_uom) {
		toast.error("Enter an item code, item group and unit of measure")
		return
	}
	const values = {
		item_name: draft.item_name.trim() || code,
		item_group: draft.item_group,
		stock_uom: draft.stock_uom,
		disabled: draft.disabled ? 1 : 0,
		standard_rate: Number(draft.standard_rate) || 0,
		is_fixed_asset: draft.is_fixed_asset ? 1 : 0,
		auto_create_assets: draft.is_fixed_asset && draft.auto_create_assets ? 1 : 0,
		purchase_uom: draft.purchase_uom || null,
		description: draft.description,
		uoms: draft.uoms.filter((r) => r.uom).map((r) => ({ uom: r.uom, conversion_factor: Number(r.conversion_factor) || 0 })),
	}
	saving.value = true
	try {
		if (doc.value) {
			await api("frappe.client.save", { doc: { ...doc.value, ...values } })
			toast.success("Item saved")
			await load()
		} else {
			const saved = await insertDoc<{ name: string }>({ doctype: "Item", item_code: code, ...values })
			toast.success(`${saved.name} created`)
			router.replace(`/items/${saved.name}`)
		}
	} finally {
		saving.value = false
	}
}

// the default unit is always a row with factor 1
watch(
	() => draft.stock_uom,
	(uom, old) => {
		if (!uom) return
		const row = draft.uoms.find((r) => r.uom === old && Number(r.conversion_factor) === 1)
		if (row) row.uom = uom
		else if (!draft.uoms.some((r) => r.uom === uom)) draft.uoms.unshift(uomRow(uom, 1))
		for (const r of draft.uoms) if (r.uom === uom) r.conversion_factor = 1
	},
	{ immediate: true },
)

function remove() {
	dialog.confirm({
		title: "Delete item?",
		message: `${doc.value.item_name} is deleted. Items used on bills cannot be deleted; disable them instead.`,
		confirmLabel: "Delete",
		theme: "red",
		onConfirm: async () => {
			await api("frappe.client.delete", { doctype: "Item", name: props.name })
			toast.success("Item deleted")
			router.replace("/items")
		},
	})
}

function openDesk() {
	window.open(`/app/item/${encodeURIComponent(props.name || "")}`, "_blank")
}

onMounted(load)
watch(() => props.name, load)
</script>
