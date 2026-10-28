<template>
	<div>
		<PageHeader
			:title="mode === 'simple' ? 'Record Expense' : 'New Journal Entry'"
			:subtitle="fromProject ? `Booked to project ${fromProject}` : mode === 'simple' ? 'Money spent from cash or bank, booked to an expense account' : 'Balanced debit and credit lines on any accounts'"
			:back="back"
		/>

		<form class="mx-auto max-w-3xl space-y-6 p-4 sm:p-6" @submit.prevent="save(true)">
			<fieldset v-if="mode === 'simple'" class="grid grid-cols-1 gap-4 rounded-xl border border-outline-gray-1 p-4 sm:grid-cols-2">
				<legend class="px-1 text-base font-semibold">Expense</legend>
				<FormControl v-model="simple.amount" v-tour="{ key: 'expense.amount', value: simple.amount }" type="number" :label="repeat ? 'Amount each time' : 'Amount'" min="0" step="0.01" required />
				<FormControl v-model="posting_date" type="date" label="Date" required />
				<div>
					<LinkField v-model="simple.expense_account" v-tour="{ key: 'expense.account', value: simple.expense_account }" doctype="Account" label="Paid from" description="Expense account (debit)" required :filters="expenseFilters" />
					<p v-if="freeHint" class="mt-1.5 text-xs" :class="over ? 'text-ink-red-4' : 'text-ink-gray-5'">{{ freeHint }}</p>
				</div>
				<LinkField v-model="simple.cost_center" v-tour="{ key: 'expense.cost_center', value: simple.cost_center }" doctype="Cost Center" label="Cost center" required :filters="{ company: session.company, is_group: 0 }" />
				<LinkField
					v-model="simple.paid_from"
					v-tour="{ key: 'expense.paid_from', value: simple.paid_from }"
					doctype="Account"
					label="Paid to"
					required
					:description="repeat ? 'Cash or bank account (credit)' : 'Cash, bank or a payable account (credit)'"
					:filters="repeat ? { company: session.company, is_group: 0, disabled: 0, account_type: ['in', ['Cash', 'Bank']] } : { company: session.company, is_group: 0, root_type: ['in', ['Asset', 'Liability']] }"
				/>
				<FormControl v-model="remark" v-tour="'expense.description'" label="Description" :required="repeat" :placeholder="repeat ? 'e.g. AWS subscription. Names the recurring payment.' : 'e.g. AWS invoice for May'" />
				<LinkField v-model="simple.project" v-tour="{ key: 'expense.project', value: simple.project }" doctype="Project" label="Project" :filters="{ company: session.company, status: 'Open' }" />
				<FormControl v-model="payee" label="Payee" placeholder="Fuel station, shop, landlord… (optional)" />
				<CategoryFields v-model:category="simple.expense_category" v-model:sub-category="simple.expense_sub_category" :project="simple.project" labels @account="useCategoryAccount" />
				<template v-if="!repeat">
					<FormControl v-model="forAsset" type="checkbox" label="For an asset" description="A running cost of an asset, such as fuel for a car" />
					<LinkField v-if="forAsset" v-model="simple.asset" doctype="Asset" label="Asset" required :filters="ASSET_FILTERS" />
					<div v-else class="hidden sm:block" />
				</template>
				<FormControl
					v-if="can('Recurring Payment', 'create')"
					v-model="repeat"
					class="sm:col-span-2"
					type="checkbox"
					label="Repeat this expense"
					description="Pay it again on the dates in the table below. It is saved as a recurring payment, and each date posts on its day."
				/>
			</fieldset>

			<fieldset v-if="mode === 'simple' && repeat" class="space-y-4 rounded-xl border border-outline-gray-1 p-4">
				<legend class="px-1 text-base font-semibold">Repeat on</legend>
				<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
					<LinkField
						v-model="budget"
						doctype="Budget"
						label="Budget"
						required
						:disabled="!!simple.project"
						:description="simple.project ? 'From the project' : 'The approved Budget the payments are taken from'"
						:filters="{ company: session.company, docstatus: 1 }"
					/>
				</div>
				<div class="flex flex-wrap items-end gap-2 rounded-lg bg-surface-gray-1 p-3">
					<FormControl v-model="fill.frequency" class="w-32" type="select" label="Repeat" :options="Object.keys(STEPS)" />
					<FormControl v-model="fill.until" class="w-40" type="date" label="until" />
					<Button label="Fill dates" :disabled="!fill.until" @click="fillDates" />
					<span class="text-xs text-ink-gray-5">Starts on the first date; the amount is the amount each time</span>
				</div>
				<ScheduleTable :rows="schedule" :placeholder="String(simple.amount || '')" :default-amount="simple.amount">
					<span class="text-sm text-ink-gray-6">{{ datedRows.length }} {{ datedRows.length === 1 ? "payment" : "payments" }} · {{ fmt(repeatTotal) }}</span>
				</ScheduleTable>
				<p v-if="room" class="text-xs" :class="outsideYear ? 'text-ink-red-4' : 'text-ink-gray-5'">
					{{ room.budget }} is for {{ room.fiscal_year }}, {{ date(room.year_start) }} – {{ date(room.year_end) }}. All dates must fall in that year.
				</p>
			</fieldset>

			<fieldset v-else-if="mode === 'journal'" class="space-y-3 rounded-xl border border-outline-gray-1 p-4">
				<legend class="px-1 text-base font-semibold">Journal lines</legend>
				<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
					<FormControl v-model="posting_date" type="date" label="Date" required />
					<FormControl v-model="remark" label="Description" />
				</div>
				<div v-for="(row, i) in lines" :key="row.key" class="grid grid-cols-1 gap-2 rounded-lg bg-surface-gray-1 p-3 sm:grid-cols-[1fr_1fr_1fr_7rem_7rem_auto] sm:items-end sm:bg-transparent sm:p-0">
					<LinkField
						v-model="row.account"
						doctype="Account"
						:label="i === 0 ? 'Account' : undefined"
						placeholder="Account"
						:query="BOOKING_ACCOUNT_QUERY"
						:filters="{ company: session.company, cost_center: row.cost_center, posting_date, expense_only: Number(row.credit) > 0 ? 0 : 1 }"
					/>
					<LinkField v-model="row.cost_center" doctype="Cost Center" :label="i === 0 ? 'Cost center' : undefined" placeholder="Cost center" :filters="{ company: session.company, is_group: 0 }" />
					<LinkField v-model="row.asset" doctype="Asset" :label="i === 0 ? 'Asset' : undefined" placeholder="Asset (optional)" :filters="ASSET_FILTERS" @update:model-value="(asset: string) => useLineAsset(row, asset)" />
					<FormControl v-model="row.debit" type="number" min="0" step="0.01" :label="i === 0 ? 'Debit' : undefined" placeholder="Debit" />
					<FormControl v-model="row.credit" type="number" min="0" step="0.01" :label="i === 0 ? 'Credit' : undefined" placeholder="Credit" />
					<Button variant="ghost" icon="lucide-trash-2" :aria-label="`Remove line ${i + 1}`" :disabled="lines.length <= 2" @click="lines.splice(i, 1)" />
				</div>
				<div class="flex flex-wrap items-center justify-between gap-2 pt-1">
					<Button v-tour="'journal.add_line'" icon-left="lucide-plus" label="Add line" @click="addLine" />
					<span class="text-sm" :class="balanced ? 'text-ink-gray-6' : 'text-ink-red-4'">
						Debit {{ fmt(totals.debit) }} · Credit {{ fmt(totals.credit) }}
						<template v-if="!balanced"> · Difference {{ fmt(totals.debit - totals.credit) }}</template>
					</span>
				</div>
			</fieldset>

			<div class="flex justify-end gap-2">
				<Button v-tour="'entry.save_draft'" label="Save Draft" :loading="saving" @click="save(false)" />
				<Button v-if="repeating && can('Recurring Payment', 'submit')" type="submit" variant="solid" :label="needsApproval('Recurring Payment') ? 'Send for Approval' : 'Save & Activate'" :loading="saving" />
				<Button v-else-if="!repeating && can('Journal Entry', 'submit')" v-tour="'entry.post'" type="submit" variant="solid" :label="needsApproval('Journal Entry') ? 'Send for Approval' : 'Post'" :loading="saving" :disabled="mode === 'journal' && !balanced" />
			</div>
		</form>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { Button, FormControl, toast } from "frappe-ui"
import CategoryFields from "@/components/CategoryFields.vue"
import LinkField from "@/components/LinkField.vue"
import PageHeader from "@/components/PageHeader.vue"
import ScheduleTable, { scheduleRow, type ScheduleRow } from "@/components/ScheduleTable.vue"
import { api, BOOKING_ACCOUNT_QUERY, getAllowedAccounts, getDoc, getRecurringRoom, insertDoc, pickAllowedAccount, type RecurringRoom } from "@/api"
import { date, money, today } from "@/format"
import { can, currency, needsApproval, session, submitOrSend } from "@/store"

// an expense is the simple form; a journal entry has free debit and credit lines
const props = defineProps<{ kind: "expense" | "journal" }>()

const route = useRoute()
const router = useRouter()
// opened with "Book Expense" on a project
const fromProject = (route.query.project as string) || ""
const mode = computed(() => (props.kind === "journal" ? "journal" : "simple"))
const back = computed(() =>
	fromProject ? { to: `/projects/${fromProject}`, label: "Project" } : mode.value === "simple" ? { to: "/expenses", label: "Expenses" } : { to: "/journals", label: "Journal Entries" },
)
const saving = ref(false)
const posting_date = ref(today())
const remark = ref("")
const fmt = (v: number) => money(v, currency.value)
let nextKey = 2
// months between dates when filling the repeat table
const STEPS: Record<string, number> = { Monthly: 1, Quarterly: 3, Yearly: 12 }

const simple = reactive({
	amount: "" as number | string,
	expense_account: "",
	cost_center: "",
	paid_from: "",
	project: fromProject,
	expense_category: "",
	expense_sub_category: "",
	asset: "",
})
type Line = { key: number; account: string; cost_center: string; asset: string; debit: number | string; credit: number | string }
const lines = reactive<Line[]>([
	{ key: 0, account: "", cost_center: "", asset: "", debit: "", credit: "" },
	{ key: 1, account: "", cost_center: "", asset: "", debit: "", credit: "" },
])

// an expense can be a running cost of an asset in use, such as fuel for a car
const forAsset = ref(false)
const ASSET_FILTERS = computed(() => ({ company: session.company, docstatus: 1, status: ["!=", "Cancelled"] }))

const totals = computed(() => ({
	debit: lines.reduce((t, l) => t + Number(l.debit || 0), 0),
	credit: lines.reduce((t, l) => t + Number(l.credit || 0), 0),
}))
const balanced = computed(() => totals.value.debit > 0 && Math.abs(totals.value.debit - totals.value.credit) < 0.005)

// "Repeat this expense" saves a recurring payment with these dates instead of one entry
const repeat = ref(false)
const repeating = computed(() => mode.value === "simple" && repeat.value)
const schedule = reactive<ScheduleRow[]>([])
const budget = ref("")
const payee = ref("")
const fill = reactive({ frequency: "Monthly", until: "" })
// what is left of the Budget (or the project's share) for the payments
const room = ref<RecurringRoom | null>(null)

const datedRows = computed(() => schedule.filter((r) => r.payment_date))
const rowAmount = (r: ScheduleRow) => Number(r.amount || simple.amount || 0)
const repeatTotal = computed(() => Math.round(datedRows.value.reduce((t, r) => t + rowAmount(r), 0) * 100) / 100)
// expenses go only to the accounts with budget on the project, else on the cost center
const allowedAccounts = ref<string[] | null>(null)
const expenseFilters = computed(() =>
	repeating.value && room.value
		? { company: session.company, name: ["in", room.value.accounts.map((a) => a.account)] }
		: allowedAccounts.value
			? { company: session.company, name: ["in", allowedAccounts.value] }
			: { company: session.company, is_group: 0, root_type: "Expense" },
)
const free = computed(() => {
	if (!repeating.value || !room.value) return null
	const account = room.value.accounts.find((a) => a.account === simple.expense_account)
	const limits = [account?.free, room.value.free].filter((v): v is number => v != null)
	return limits.length ? Math.min(...limits) : null
})
const over = computed(() => free.value != null && repeatTotal.value > free.value)
const freeHint = computed(() => {
	if (free.value == null || !simple.expense_account) return ""
	return `${fmt(Math.max(free.value, 0))} free ${room.value!.share ? `of the share of ${simple.project}` : `on ${room.value!.budget}`}`
})
const outsideYear = computed(() => !!room.value && datedRows.value.some((r) => r.payment_date < room.value!.year_start || r.payment_date > room.value!.year_end))

watch(repeat, (on) => {
	if (on && !schedule.length) schedule.push(scheduleRow(posting_date.value, simple.amount))
})

// the same day every `step` months, from the first date until `fill.until`
function fillDates() {
	const first = schedule.find((r) => r.payment_date)?.payment_date || posting_date.value
	const step = STEPS[fill.frequency]
	const rows: ScheduleRow[] = []
	for (let i = 0, d = first; d <= fill.until && i < 120; d = addMonths(first, ++i * step)) rows.push(scheduleRow(d, simple.amount))
	schedule.splice(0, schedule.length, ...rows)
}

function addMonths(iso: string, months: number) {
	const [y, m, d] = iso.split("-").map(Number)
	const lastDay = new Date(Date.UTC(y, m - 1 + months + 1, 0)).getUTCDate()
	return new Date(Date.UTC(y, m - 1 + months, Math.min(d, lastDay))).toISOString().slice(0, 10)
}

watch(
	() => [repeating.value, simple.project, budget.value],
	async () => {
		const project = simple.project
		const chosen = budget.value
		if (!repeating.value || (!project && !chosen)) {
			room.value = null
			return
		}
		const result = await getRecurringRoom(project ? undefined : chosen, project || undefined, true).catch(() => null)
		if (project !== simple.project || (!project && chosen !== budget.value)) return
		room.value = result
		if (!result) return
		if (project) budget.value = result.budget
		// the payments must use the Budget's accounts and a cost center under it
		const accounts = result.accounts.map((a) => a.account)
		if (!accounts.includes(simple.expense_account)) simple.expense_account = accounts.length === 1 ? accounts[0] : ""
		if (result.default_cost_center) simple.cost_center = result.default_cost_center
	},
)

function addLine() {
	const diff = totals.value.debit - totals.value.credit
	lines.push({ key: nextKey++, account: "", cost_center: "", asset: "", debit: diff < 0 ? -diff : "", credit: diff > 0 ? diff : "" })
}

function buildAccounts() {
	if (mode.value === "simple") {
		const amount = Number(simple.amount)
		return {
			voucher_type: "Expense Entry",
			accounts: [
				{
					account: simple.expense_account,
					cost_center: simple.cost_center,
					project: simple.project || undefined,
					expense_category: simple.expense_category || undefined,
					expense_sub_category: simple.expense_sub_category || undefined,
					asset: (forAsset.value && simple.asset) || undefined,
					debit: amount,
				},
				{ account: simple.paid_from, credit: amount },
			],
		}
	}
	return {
		voucher_type: "Journal Entry",
		accounts: lines
			.filter((l) => l.account)
			.map((l) => ({ account: l.account, cost_center: l.cost_center || undefined, asset: l.asset || undefined, debit: Number(l.debit || 0), credit: Number(l.credit || 0) })),
	}
}

async function save(post: boolean) {
	if (repeating.value) return saveRecurring(post)
	saving.value = true
	try {
		const saved = await insertDoc<{ name: string }>({
			doctype: "Journal Entry",
			company: session.company,
			posting_date: posting_date.value,
			user_remark: remark.value,
			payee: (mode.value === "simple" && payee.value) || undefined,
			...buildAccounts(),
		})
		const sent = post && (await submitOrSend("Journal Entry", saved.name))
		toast.success(sent ? `${saved.name} sent for approval` : post ? `Posted ${saved.name}` : `Draft ${saved.name} saved`)
		router.push(fromProject && simple.project === fromProject ? `/projects/${fromProject}` : `${mode.value === "simple" ? "/expenses" : "/journals"}/${saved.name}`)
	} finally {
		saving.value = false
	}
}

async function saveRecurring(activate: boolean) {
	const title = remark.value.trim()
	if (!title || !datedRows.value.length) {
		toast.error(title ? "Add the dates to pay on" : "Enter a description. It names the recurring payment.")
		return
	}
	const dates = datedRows.value.map((r) => r.payment_date).sort()
	const payload: Record<string, any> = {
		doctype: "Recurring Payment",
		company: session.company,
		title,
		payee: payee.value,
		expense_account: simple.expense_account,
		cost_center: simple.cost_center,
		paid_from: simple.paid_from,
		project: simple.project,
		expense_category: simple.expense_category,
		expense_sub_category: simple.expense_sub_category,
		budget: budget.value,
		frequency: "Custom",
		from_date: dates[0],
		to_date: dates[dates.length - 1],
		total_amount: repeatTotal.value,
		schedule: datedRows.value.map((r) => ({ payment_date: r.payment_date, amount: rowAmount(r) })),
	}
	for (const key of ["project", "cost_center", "payee", "expense_category", "expense_sub_category"]) if (!payload[key]) delete payload[key]
	if (payload.project) delete payload.budget // the server takes it from the project
	saving.value = true
	try {
		const saved = await insertDoc<{ name: string }>(payload)
		const sent = activate && (await submitOrSend("Recurring Payment", saved.name))
		// dates up to today post now instead of waiting for the daily job
		const posted = activate && !sent ? await api<string[]>("spend.purchasing.doctype.recurring_payment.recurring_payment.post_due_payments", { name: saved.name }) : []
		toast.success(
			sent ? `${saved.name} sent for approval` : activate ? `${saved.name} is active${posted.length ? `, ${posted.length} posted today` : ""}` : `Draft ${saved.name} saved`,
		)
		router.push(`/recurring/${saved.name}`)
	} finally {
		saving.value = false
	}
}

// a project's own cost center replaces the company default; an asset's replaces both
async function useProjectCostCenter() {
	const project = simple.project
	if (!project || (forAsset.value && simple.asset)) return
	const { cost_center } = await getDoc<{ cost_center?: string }>("Project", project)
	if (cost_center && project === simple.project) simple.cost_center = cost_center
}

type AssetPlace = { cost_center?: string; project?: string }

// the asset's cost center replaces the company default, and its project fills an empty one
async function useAsset() {
	const asset = simple.asset
	if (!asset) return
	const { cost_center, project } = await getDoc<AssetPlace>("Asset", asset)
	if (asset !== simple.asset) return
	if (cost_center) simple.cost_center = cost_center
	if (project && !simple.project) simple.project = project
}

async function useLineAsset(row: Line, asset: string) {
	if (!asset || row.cost_center) return
	const { cost_center } = await getDoc<AssetPlace>("Asset", asset)
	if (asset === row.asset && cost_center && !row.cost_center) row.cost_center = cost_center
}

async function useAllowedAccounts() {
	const line = { project: simple.project, cost_center: simple.cost_center, posting_date: posting_date.value }
	const accounts = await getAllowedAccounts(session.company, line)
	if (line.project !== simple.project || line.cost_center !== simple.cost_center || line.posting_date !== posting_date.value) return
	allowedAccounts.value = accounts
	if (simple.expense_account) simple.expense_account = pickAllowedAccount(simple.expense_account, accounts)
	else if (accounts?.length === 1) simple.expense_account = accounts[0]
}

function useCategoryAccount(account: string) {
	simple.expense_account = pickAllowedAccount(account, allowedAccounts.value)
}

// another project has other categories
watch(
	() => simple.project,
	() => {
		Object.assign(simple, { expense_category: "", expense_sub_category: "" })
		useProjectCostCenter()
	},
)
watch(() => simple.asset, useAsset)
watch(forAsset, (on) => on || (simple.asset = ""))
// and another project, cost center or year other budgeted accounts
watch(() => [simple.project, simple.cost_center, posting_date.value], useAllowedAccounts)

onMounted(async () => {
	const defaults = await api("spend.spend.doctype.company.company.get_company_defaults", { company: session.company })
	Object.assign(simple, {
		expense_account: simple.expense_account || defaults.default_expense_account || "",
		cost_center: defaults.default_cost_center || "",
		paid_from: defaults.default_cash_account || "",
	})
	await useProjectCostCenter()
})
</script>
