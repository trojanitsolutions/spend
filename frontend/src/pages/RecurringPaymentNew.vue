<template>
	<div>
		<PageHeader
			:title="amendOf ? `Amend ${amendOf}` : 'New Recurring Payment'"
			:subtitle="amendOf ? 'Covers what is still unpaid. It replaces the cancelled one once it is approved.' : 'Splits the total over the dates and posts each payment on its date'"
			:back="amendOf ? { to: `/recurring/${amendOf}`, label: amendOf } : { to: '/recurring', label: 'Recurring Payments' }"
		>
			<template #actions>
				<Button label="Save Draft" :loading="saving" @click="save(false)" />
				<Button v-if="can('Recurring Payment', 'submit')" variant="solid" :label="needsApproval('Recurring Payment') ? 'Save & Send for Approval' : 'Save & Activate'" :loading="saving" @click="save(true)" />
			</template>
		</PageHeader>

		<div v-if="loading" class="p-6"><LoadingText /></div>
		<form v-else class="mx-auto max-w-4xl space-y-6 p-4 sm:p-6" @submit.prevent="save(false)">
			<fieldset v-if="amendOf" class="space-y-3 rounded-xl border border-outline-gray-1 p-4">
				<legend class="px-1 text-base font-semibold">Amendment</legend>
				<p v-if="paidBefore?.payments" class="rounded-lg bg-surface-gray-2 p-3 text-sm text-ink-gray-7">
					{{ amendOf }} already paid {{ fmt(paidBefore.paid_amount) }} in {{ paidBefore.payments }} {{ paidBefore.payments === 1 ? "payment" : "payments" }}, the last on
					{{ date(paidBefore.last_paid) }}. Those stay on the books; this amendment covers the rest and must start after that date.
				</p>
				<FormControl v-model="doc.amendment_reason" type="textarea" label="Reason for amendment" required placeholder="What changed and why? Approvers see this." />
			</fieldset>
			<fieldset class="grid grid-cols-1 gap-4 rounded-xl border border-outline-gray-1 p-4 sm:grid-cols-2">
				<legend class="px-1 text-base font-semibold">Payment</legend>
				<FormControl v-model="doc.title" label="Title" required placeholder="e.g. Office rent" />
				<FormControl v-model="doc.payee" label="Payee" placeholder="Landlord, provider… (optional)" />
				<LinkField v-model="doc.project" doctype="Project" label="Project" description="Optional. The payment then takes from the project's share." :filters="{ company: session.company, status: 'Open' }" />
				<CategoryFields
					v-model:category="doc.expense_category"
					v-model:sub-category="doc.expense_sub_category"
					:project="doc.project"
					labels
					@account="useCategoryAccount"
				/>
				<LinkField
					v-model="doc.budget"
					doctype="Budget"
					label="Budget"
					required
					:disabled="!!doc.project"
					:description="doc.project ? 'From the project' : 'The approved Budget the payment is taken from'"
					:filters="{ company: session.company, docstatus: 1 }"
				/>
				<div>
					<LinkField
						v-model="doc.expense_account"
						doctype="Account"
						label="Paid from"
						description="Expense account (debit)"
						required
						:disabled="!room"
						:filters="{ company: session.company, name: ['in', room ? room.accounts.map((a) => a.account) : []] }"
					/>
					<p v-if="freeHint" class="mt-1.5 text-xs" :class="over ? 'text-ink-red-4' : 'text-ink-gray-5'">{{ freeHint }}</p>
				</div>
				<LinkField v-model="doc.cost_center" doctype="Cost Center" label="Cost center" :disabled="!room" :description="room ? `Under ${room.cost_center}` : undefined" :filters="costCenterFilters" />
				<LinkField
					v-model="doc.paid_from"
					doctype="Account"
					label="Paid to"
					required
					description="Cash or bank account (credit)"
					:filters="{ company: session.company, is_group: 0, disabled: 0, account_type: ['in', ['Cash', 'Bank']] }"
				/>
			</fieldset>

			<fieldset class="grid grid-cols-1 gap-4 rounded-xl border border-outline-gray-1 p-4 sm:grid-cols-2">
				<legend class="px-1 text-base font-semibold">Schedule</legend>
				<FormControl v-model="doc.from_date" type="date" label="From date" required />
				<FormControl v-model="doc.to_date" type="date" label="To date" required />
				<p v-if="room" class="text-xs sm:col-span-2" :class="outsideYear ? 'text-ink-red-4' : 'text-ink-gray-5'">
					{{ room.budget }} is for {{ room.fiscal_year }}, {{ date(room.year_start) }} – {{ date(room.year_end) }}. All payments must fall in that year.
				</p>
				<FormControl v-model="doc.frequency" type="select" label="Frequency" :options="FREQUENCIES" />
				<FormControl v-model="doc.total_amount" type="number" min="0" step="0.01" label="Total amount" required :class="{ over }" description="Split across the payment dates" />
			</fieldset>

			<fieldset class="rounded-xl border border-outline-gray-1">
				<legend class="ml-4 px-1 text-base font-semibold">Payments</legend>
				<template v-if="custom">
					<ScheduleTable class="p-4" :rows="customRows" :placeholder="evenShare">
						<span class="text-sm" :class="customMismatch ? 'text-ink-red-4' : 'text-ink-gray-6'">{{ customHint }}</span>
					</ScheduleTable>
				</template>
				<p v-else-if="!preview.length" class="px-4 py-8 text-center text-sm text-ink-gray-5">Enter the dates, frequency and total to see each payment.</p>
				<DataTable v-else :columns="previewColumns" :rows="preview" row-key="payment_date" />
				<div v-if="!custom && preview.length" class="flex justify-end border-t border-outline-gray-1 px-4 py-3 text-sm text-ink-gray-6">
					{{ preview.length }} payments · {{ fmt(Number(doc.total_amount)) }}
				</div>
			</fieldset>

			<FormControl v-model="doc.remarks" type="textarea" label="Remarks" />
		</form>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { Button, FormControl, LoadingText, toast } from "frappe-ui"
import DataTable, { type Column } from "@/components/DataTable.vue"
import CategoryFields from "@/components/CategoryFields.vue"
import LinkField from "@/components/LinkField.vue"
import PageHeader from "@/components/PageHeader.vue"
import ScheduleTable, { scheduleRow, type ScheduleRow } from "@/components/ScheduleTable.vue"
import { api, getAmendment, getRecurringRoom, insertDoc, type RecurringRoom } from "@/api"
import { date, money, today } from "@/format"
import { can, currency, needsApproval, session, submitOrSend } from "@/store"

const FREQUENCIES = ["Monthly", "Quarterly", "Yearly", "Custom"]

const route = useRoute()
const router = useRouter()
const amendOf = (route.query.amend as string) || ""
const loading = ref(!!amendOf)
const paidBefore = ref<any>(null)
const saving = ref(false)
const preview = ref<{ payment_date: string; amount: number }[]>([])
const room = ref<RecurringRoom | null>(null)
const fmt = (v: number) => money(v, currency.value)

const doc = reactive({
	title: "",
	payee: "",
	expense_account: "",
	paid_from: "",
	project: (route.query.project as string) || "",
	expense_category: "",
	expense_sub_category: "",
	budget: "",
	cost_center: "",
	from_date: today(),
	to_date: "",
	frequency: "Monthly",
	total_amount: "" as number | string,
	remarks: "",
	amendment_reason: "",
})
const customRows = reactive<ScheduleRow[]>([])

const custom = computed(() => doc.frequency === "Custom")
const previewColumns: Column[] = [
	{ key: "payment_date", label: "Date", format: date },
	{ key: "amount", label: "Amount", align: "right", format: (v) => fmt(v) },
]

const datedRows = computed(() => customRows.filter((r) => r.payment_date))
const evenShare = computed(() => (datedRows.value.length && Number(doc.total_amount) ? (Number(doc.total_amount) / datedRows.value.length).toFixed(2) : "0.00"))
const enteredTotal = computed(() => Math.round(datedRows.value.reduce((t, r) => t + Number(r.amount || 0), 0) * 100) / 100)
const anyAmount = computed(() => datedRows.value.some((r) => Number(r.amount)))
const customMismatch = computed(() => anyAmount.value && Math.abs(enteredTotal.value - Number(doc.total_amount || 0)) >= 0.01)
const customHint = computed(() => {
	if (!datedRows.value.length) return "Add the payment dates"
	if (!anyAmount.value) return `${datedRows.value.length} dates · total split evenly`
	const left = Math.round((Number(doc.total_amount || 0) - enteredTotal.value) * 100) / 100
	return left ? `${fmt(Math.abs(left))} ${left > 0 ? "left to allocate" : "over the total"}` : "Amounts match the total"
})

async function loadPreview() {
	if (custom.value || !doc.from_date || !doc.to_date || !(Number(doc.total_amount) > 0)) {
		preview.value = []
		return
	}
	preview.value = await api(
		"spend.purchasing.doctype.recurring_payment.recurring_payment.preview_schedule",
		{ from_date: doc.from_date, to_date: doc.to_date, frequency: doc.frequency, total_amount: doc.total_amount },
		{ silent: true },
	).catch(() => [])
}

watch(() => [doc.from_date, doc.to_date, doc.frequency, doc.total_amount], loadPreview)
watch(custom, (on) => {
	if (on && !customRows.length) for (const row of preview.value.length ? preview.value : [{ payment_date: doc.from_date }]) customRows.push(scheduleRow(row.payment_date))
})

// the smaller of what is free on the account and in total
const free = computed(() => {
	if (!room.value) return null
	const account = room.value.accounts.find((a) => a.account === doc.expense_account)
	const limits = [account?.free, room.value.free].filter((v): v is number => v != null)
	return limits.length ? Math.min(...limits) : null
})
const over = computed(() => free.value != null && Number(doc.total_amount || 0) > free.value)
const freeHint = computed(() => {
	if (free.value == null || !doc.expense_account) return ""
	return `${fmt(Math.max(free.value, 0))} free ${room.value!.share ? `of the share of ${doc.project}` : `on ${room.value!.budget}`}`
})
const outsideYear = computed(() => !!room.value && ((!!doc.from_date && doc.from_date < room.value.year_start) || (!!doc.to_date && doc.to_date > room.value.year_end)))
const costCenterFilters = computed(() => {
	const filters: Record<string, any> = { company: session.company, is_group: 0, disabled: 0 }
	if (room.value) Object.assign(filters, { lft: [">=", room.value.lft], rgt: ["<=", room.value.rgt] })
	return filters
})

// the category's account, when the Budget has it
function useCategoryAccount(account: string) {
	if (!room.value || room.value.accounts.some((a) => a.account === account)) doc.expense_account = account
	else toast.info(`${account} is not on ${room.value.budget}. Pick one of its accounts.`)
}

// an amendment keeps its saved values; otherwise the Budget fills them in
let keepValues = !!amendOf
watch(
	() => (doc.project ? `project:${doc.project}` : `budget:${doc.budget}`),
	async () => {
		const { project, budget } = doc
		room.value = null
		if (!project && !budget) return
		const result = await getRecurringRoom(project ? undefined : budget, project || undefined).catch(() => null)
		if (project !== doc.project || (!project && budget !== doc.budget)) return
		room.value = result
		if (!result) return
		if (project) doc.budget = result.budget
		if (keepValues) {
			keepValues = false
			return
		}
		doc.cost_center = result.default_cost_center || ""
		const accounts = result.accounts.map((a) => a.account)
		if (!accounts.includes(doc.expense_account)) doc.expense_account = accounts.length === 1 ? accounts[0] : ""
		if (!doc.from_date || doc.from_date < result.year_start || doc.from_date > result.year_end) doc.from_date = result.year_start
		if (!doc.to_date || doc.to_date > result.year_end || doc.to_date < doc.from_date) doc.to_date = result.year_end
	},
	{ immediate: true },
)

async function loadAmendment() {
	const result = await getAmendment<any>("Recurring Payment", amendOf)
	if (result.existing) {
		toast.info(`${amendOf} already has an open amendment`)
		router.replace(`/recurring/${result.existing}`)
		return
	}
	const copy = result.doc
	for (const key of Object.keys(doc) as (keyof typeof doc)[]) if (key !== "amendment_reason") (doc as any)[key] = copy[key] ?? ""
	if (copy.frequency === "Custom") for (const row of copy.schedule) customRows.push(scheduleRow(row.payment_date, row.amount))
	paidBefore.value = result.previous
	loading.value = false
}

async function save(submit: boolean) {
	saving.value = true
	try {
		const payload: Record<string, any> = { doctype: "Recurring Payment", company: session.company, ...doc }
		if (amendOf) payload.amended_from = amendOf
		else delete payload.amendment_reason
		if (custom.value) payload.schedule = datedRows.value.map((r) => ({ payment_date: r.payment_date, amount: anyAmount.value ? Number(r.amount || 0) : 0 }))
		for (const key of ["project", "cost_center", "payee", "expense_category", "expense_sub_category"]) if (!payload[key]) delete payload[key]
		if (payload.project) delete payload.budget // the server takes it from the project
		const saved = await insertDoc<{ name: string }>(payload)
		const sent = submit && (await submitOrSend("Recurring Payment", saved.name))
		toast.success(sent ? `${saved.name} sent for approval` : submit ? `${saved.name} is active` : `Draft ${saved.name} saved`)
		router.replace(`/recurring/${saved.name}`)
	} finally {
		saving.value = false
	}
}

onMounted(async () => {
	if (amendOf) await loadAmendment()
	const defaults = await api("spend.spend.doctype.company.company.get_company_defaults", { company: session.company })
	doc.paid_from ||= defaults.default_cash_account || ""
})
</script>

<style scoped>
.over :deep(input) {
	border-color: var(--outline-red-3, #f87171);
}
</style>
