<template>
	<div>
		<PageHeader title="New Bill" subtitle="Records what you owe a supplier and books the expense" :back="{ to: '/bills', label: 'Bills' }">
			<template #actions>
				<Button v-tour="'bill.save_draft'" label="Save Draft" :loading="saving" @click="save(false)" />
				<Button v-if="can('Purchase Invoice', 'submit')" v-tour="'bill.submit'" variant="solid" :label="needsApproval('Purchase Invoice') ? 'Save & Send for Approval' : 'Save & Submit'" :loading="saving" @click="save(true)" />
			</template>
		</PageHeader>

		<form class="mx-auto max-w-4xl space-y-6 p-4 sm:p-6" @submit.prevent="save(false)">
			<fieldset class="grid grid-cols-1 gap-4 card p-4 sm:grid-cols-2">
				<legend class="px-1 text-base font-semibold">Bill</legend>
				<LinkField v-model="doc.supplier" v-tour="{ key: 'bill.supplier', value: doc.supplier }" doctype="Supplier" label="Supplier" required :filters="{ disabled: 0 }" />
				<FormControl v-model="doc.bill_no" v-tour="'bill.bill_no'" label="Supplier invoice no." placeholder="As printed on the bill" />
				<FormControl v-model="doc.posting_date" v-tour="{ key: 'bill.posting_date', value: doc.posting_date }" type="date" label="Posting date" required />
				<FormControl v-model="doc.due_date" v-tour="{ key: 'bill.due_date', value: doc.due_date }" type="date" label="Due date" required />
				<FormControl v-model="doc.bill_date" type="date" label="Supplier invoice date" />
				<LinkField v-model="doc.cost_center" v-tour="{ key: 'bill.cost_center', value: doc.cost_center }" doctype="Cost Center" label="Default cost center" :filters="{ company: session.company, is_group: 0, disabled: 0 }" />
				<LinkField v-model="doc.project" v-tour="{ key: 'bill.project', value: doc.project }" doctype="Project" label="Project" description="Tags every line without its own project" :filters="projectFilters" />
			</fieldset>

			<fieldset class="space-y-3 card p-4">
				<legend class="px-1 text-base font-semibold">Items</legend>
				<div v-for="(item, i) in items" :key="item.key" class="space-y-2 rounded-lg bg-surface-gray-1 p-3 sm:bg-transparent sm:p-0" :class="{ 'sm:border-t sm:border-outline-gray-1 sm:pt-3': i > 0 }">
					<div class="grid grid-cols-2 gap-2 sm:grid-cols-[minmax(0,2fr)_5rem_6rem_7rem_minmax(7rem,max-content)_auto] sm:items-end">
						<div class="col-span-2 flex items-end gap-1 sm:col-span-1">
							<LinkField
								class="min-w-0 flex-1"
								v-tour="{ key: lineKey('item', i), value: item.item_code }"
								:model-value="item.item_code"
								doctype="Item"
								:label="i === 0 ? 'Item' : undefined"
								placeholder="Pick an item"
								:filters="{ disabled: 0 }"
								@update:model-value="(code: string) => setItem(item, code)"
							/>
							<Button v-if="can('Item', 'create')" variant="ghost" icon="lucide-plus" aria-label="New item" title="New item" @click="creatingFor = item" />
						</div>
						<FormControl v-model="item.qty" v-tour="{ key: lineKey('qty', i), value: item.qty }" type="number" min="0" step="any" :label="i === 0 ? 'Qty' : undefined" placeholder="1" />
						<FormControl
							type="select"
							:model-value="item.uom"
							:label="i === 0 ? 'UOM' : undefined"
							:options="item.uoms.length ? item.uoms : [{ label: '—', value: '' }]"
							:disabled="!item.item_code"
							@update:model-value="(uom: string) => setUom(item, uom)"
						/>
						<FormControl v-model="item.rate" v-tour="{ key: lineKey('rate', i), value: item.rate }" type="number" min="0" step="0.01" :label="i === 0 ? `Rate${item.uom ? ' / ' + item.uom : ''}` : undefined" placeholder="0.00" />
						<div class="flex h-7 min-w-0 items-center justify-end whitespace-nowrap text-base tabular-nums text-ink-gray-8" :class="{ 'sm:mt-5': i === 0 }" :title="i === 0 ? 'Amount' : undefined">
							{{ fmt(amount(item)) }}
						</div>
						<div class="col-span-2 flex justify-end gap-1 sm:col-span-1">
							<Button
								variant="ghost"
								icon="lucide-pencil"
								:class="{ 'bg-surface-gray-3': item.open }"
								:aria-label="`Edit details of item ${i + 1}`"
								title="Account, cost center, project and category"
								@click="item.open = !item.open"
							/>
							<Button variant="ghost" icon="lucide-trash-2" :aria-label="`Remove item ${i + 1}`" :disabled="items.length <= 1" @click="items.splice(i, 1)" />
						</div>
					</div>
					<div v-if="!item.open && item.item_code" class="flex flex-wrap items-center gap-x-2 text-sm text-ink-gray-5">
						<Badge v-if="item.is_fixed_asset" theme="blue" label="Fixed asset" />
						<span class="truncate">{{ lineSummary(item) }}</span>
					</div>
					<div v-if="item.open" class="grid grid-cols-1 gap-3 rounded-lg border border-outline-gray-2 p-3 sm:grid-cols-2">
						<FormControl v-model="item.description" class="sm:col-span-2" type="textarea" :rows="2" label="Description" placeholder="From the item" />
						<LinkField
							v-model="item.expense_account"
							doctype="Account"
							:label="item.is_fixed_asset ? 'Asset account' : 'Expense account'"
							:placeholder="item.default_account || defaultExpense || 'Account'"
							:description="item.is_fixed_asset ? 'Empty uses the Fixed Asset Account of the company' : 'Empty uses the category, the item group, then the company default'"
							:filters="lineAccountFilters(item)"
						/>
						<FormControl
							:model-value="item.item_code ? `1 ${item.uom} = ${item.conversion_factor} ${item.stock_uom} · ${stockQty(item)} ${item.stock_uom} in all` : '—'"
							label="Conversion to default unit"
							disabled
						/>
						<LinkField v-model="item.cost_center" doctype="Cost Center" label="Cost center" :placeholder="doc.cost_center || 'Cost center'" :filters="{ company: session.company, is_group: 0, disabled: 0 }" />
						<LinkField v-model="item.project" doctype="Project" label="Project" :placeholder="doc.project || 'No project'" :filters="projectFilters" />
						<CategoryFields
							v-if="!item.is_fixed_asset"
							v-model:category="item.expense_category"
							v-model:sub-category="item.expense_sub_category"
							:project="item.project || doc.project"
							:labels="true"
							@account="(a) => useCategoryAccount(item, a)"
						/>
					</div>
				</div>
				<div class="flex flex-wrap items-center justify-between gap-2 pt-1">
					<Button v-tour="'bill.add_item'" icon-left="lucide-plus" label="Add item" @click="addItem" />
					<span v-tour="{ key: 'bill.total', value: total }" class="text-base font-semibold tabular-nums">Total {{ fmt(total) }}</span>
				</div>
			</fieldset>

			<FormControl v-model="doc.remarks" v-tour="'bill.remarks'" type="textarea" label="Remarks" />
		</form>
		<ItemDialog :open="!!creatingFor" @update:open="(v) => !v && (creatingFor = null)" @saved="useCreatedItem" />
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { Badge, Button, FormControl, toast } from "frappe-ui"
import CategoryFields from "@/components/CategoryFields.vue"
import ItemDialog from "@/components/ItemDialog.vue"
import LinkField from "@/components/LinkField.vue"
import PageHeader from "@/components/PageHeader.vue"
import { api, getAllowedAccounts, getDoc, insertDoc, pickAllowedAccount } from "@/api"
import { addDays, money, today } from "@/format"
import { can, currency, needsApproval, session, submitOrSend } from "@/store"

const PAYMENT_TERMS_DAYS = 30

/** Training keys of a line's fields: `bill.qty` on the first line, `bill.qty.2` on the second. */
const lineKey = (field: string, i: number) => (i ? `bill.${field}.${i + 1}` : `bill.${field}`)

const route = useRoute()
const router = useRouter()
const saving = ref(false)
const fmt = (v: number) => money(v, currency.value)
let nextKey = 1

const doc = reactive({
	supplier: (route.query.supplier as string) || "",
	bill_no: "",
	posting_date: today(),
	due_date: addDays(today(), PAYMENT_TERMS_DAYS),
	bill_date: "",
	cost_center: "",
	project: (route.query.project as string) || "",
	remarks: "",
})
const defaultExpense = ref("")
const items = reactive([newItem()])
const creatingFor = ref<Line | null>(null)

const projectFilters = computed(() => ({ company: session.company, status: "Open" }))
const accountFilters = computed(() => ({ company: session.company, is_group: 0, disabled: 0 }))
const total = computed(() => items.reduce((t, item) => t + amount(item), 0))
// expenses go only to the accounts with budget on the line's project, else on its cost center
const accountsFor = reactive<Record<string, string[] | null>>({})

type Line = ReturnType<typeof newItem>

function newItem() {
	return {
		key: nextKey++,
		open: false,
		item_code: "",
		description: "",
		uom: "",
		uoms: [] as { label: string; value: string }[],
		stock_uom: "",
		conversion_factor: 1,
		is_fixed_asset: 0,
		default_account: "",
		expense_account: "",
		cost_center: "",
		project: "",
		expense_category: "",
		expense_sub_category: "",
		qty: 1 as number | string,
		rate: "" as number | string,
	}
}

const amount = (item: Line) => Math.round(Number(item.qty || 0) * Number(item.rate || 0) * 100) / 100

const stockQty = (item: Line) => Math.round(Number(item.qty || 0) * item.conversion_factor * 1e6) / 1e6

function lineSummary(item: Line) {
	const account = item.expense_account || item.default_account
	const parts = [item.conversion_factor !== 1 && `${stockQty(item)} ${item.stock_uom}`, account, item.project || doc.project, item.expense_sub_category || item.expense_category]
	return parts.filter(Boolean).join(" · ")
}

// as ERPNext: the item fills its purchase unit, the supplier's last rate, its group's account and cost center
async function setItem(item: Line, code: string) {
	item.item_code = code
	if (!code) return
	const d = await api("spend.purchasing.doctype.item.item.get_item_details", { item_code: code, company: session.company, supplier: doc.supplier || undefined })
	Object.assign(item, {
		description: d.description || "",
		uom: d.uom,
		uoms: d.uoms.map((u: string) => ({ label: u, value: u })),
		stock_uom: d.stock_uom,
		conversion_factor: d.conversion_factor,
		is_fixed_asset: d.is_fixed_asset,
		default_account: d.expense_account || "",
		expense_account: "",
		rate: d.rate || "",
	})
	if (d.is_fixed_asset) Object.assign(item, { expense_category: "", expense_sub_category: "" })
	if (d.cost_center && !item.cost_center) item.cost_center = d.cost_center
}

// a new unit keeps the price of the default unit
async function setUom(item: Line, uom: string) {
	if (!uom || uom === item.uom) return
	const { conversion_factor } = await api("spend.purchasing.doctype.item.item.get_uom_details", { item_code: item.item_code, uom })
	if (item.rate !== "") item.rate = Math.round((Number(item.rate) / item.conversion_factor) * conversion_factor * 100) / 100
	Object.assign(item, { uom, conversion_factor })
}

function useCreatedItem(code: string) {
	if (creatingFor.value) setItem(creatingFor.value, code)
	creatingFor.value = null
}

function addItem() {
	items.push(newItem())
}

// a project's own cost center replaces the company default
async function useProjectCostCenter() {
	if (!doc.project) return
	const { cost_center } = await getDoc<{ cost_center?: string }>("Project", doc.project)
	if (cost_center) doc.cost_center = cost_center
}

watch(() => doc.project, useProjectCostCenter)

function lineScope(item: Line) {
	return { project: item.project || doc.project, cost_center: item.cost_center || doc.cost_center, posting_date: doc.posting_date }
}

const scopeKey = (scope: ReturnType<typeof lineScope>) => (scope.project ? `project:${scope.project}` : scope.cost_center ? `${scope.cost_center}|${scope.posting_date}` : "")

function allowedAccounts(item: Line) {
	const key = scopeKey(lineScope(item))
	return !item.is_fixed_asset && key ? accountsFor[key] : undefined
}

function lineAccountFilters(item: Line) {
	const allowed = allowedAccounts(item)
	if (allowed) return { company: session.company, name: ["in", allowed] }
	return { ...accountFilters.value, root_type: item.is_fixed_asset ? "Asset" : "Expense" }
}

function useCategoryAccount(item: Line, account: string) {
	item.expense_account = pickAllowedAccount(account, allowedAccounts(item))
}

watch(
	() => items.map((item) => scopeKey(lineScope(item))),
	async () => {
		for (const item of items) {
			const scope = lineScope(item)
			const key = scopeKey(scope)
			if (key && !(key in accountsFor)) accountsFor[key] = await getAllowedAccounts(session.company, scope)
		}
		for (const item of items) {
			if (item.expense_account) item.expense_account = pickAllowedAccount(item.expense_account, allowedAccounts(item))
		}
	},
	{ immediate: true },
)

watch(
	() => doc.posting_date,
	(value, old) => {
		if (value && (!doc.due_date || doc.due_date === addDays(old, PAYMENT_TERMS_DAYS))) doc.due_date = addDays(value, PAYMENT_TERMS_DAYS)
	},
)

async function save(submit: boolean) {
	const lines = items.filter((item) => item.item_code || amount(item))
	if (!lines.length) {
		toast.error("Add at least one item")
		return
	}
	if (lines.some((item) => !item.item_code)) {
		toast.error("Pick an item on every line")
		return
	}
	saving.value = true
	try {
		const payload: Record<string, any> = {
			doctype: "Purchase Invoice",
			company: session.company,
			...doc,
			items: lines.map((item) => ({
				item_code: item.item_code,
				description: item.description || undefined,
				uom: item.uom || undefined,
				conversion_factor: item.conversion_factor,
				expense_account: item.expense_account || undefined,
				cost_center: item.cost_center || undefined,
				project: item.project || undefined,
				expense_category: item.expense_category || undefined,
				expense_sub_category: item.expense_sub_category || undefined,
				qty: Number(item.qty || 0),
				rate: Number(item.rate || 0),
			})),
		}
		if (!payload.bill_date) delete payload.bill_date
		if (!payload.project) delete payload.project
		const saved = await insertDoc<{ name: string }>(payload)
		const sent = submit && (await submitOrSend("Purchase Invoice", saved.name))
		toast.success(sent ? `Bill ${saved.name} sent for approval` : submit ? `Bill ${saved.name} submitted` : `Draft ${saved.name} saved`)
		router.replace(`/bills/${saved.name}`)
	} finally {
		saving.value = false
	}
}

onMounted(async () => {
	const defaults = await api("spend.spend.doctype.company.company.get_company_defaults", { company: session.company })
	doc.cost_center = defaults.default_cost_center || ""
	await useProjectCostCenter()
	defaultExpense.value = defaults.default_expense_account || ""
})
</script>
