<template>
	<div>
		<PageHeader :title="amendOf ? `Amend ${amendOf}` : 'New Budget'" :subtitle="amendOf ? 'The amendment replaces the cancelled budget once it is approved' : undefined" :back="back">
			<template #actions>
				<Button label="Save Draft" :loading="saving" :disabled="loading" @click="save(false)" />
				<Button v-if="can('Budget', 'submit')" variant="solid" :label="needsApproval('Budget') ? 'Save & Send for Approval' : 'Save & Submit'" :loading="saving" :disabled="loading" @click="save(true)" />
			</template>
		</PageHeader>

		<div v-if="loading" class="p-6"><LoadingText /></div>
		<form v-else class="mx-auto max-w-3xl space-y-6 p-4 sm:p-6" @submit.prevent="save(false)">
			<fieldset v-if="amendOf" class="card p-4">
				<legend class="px-1 text-base font-semibold">Amendment</legend>
				<FormControl v-model="doc.amendment_reason" type="textarea" label="Reason for amendment" required placeholder="What changed and why? Approvers see this." />
			</fieldset>

			<fieldset class="grid grid-cols-1 gap-4 card p-4 sm:grid-cols-2">
				<legend class="px-1 text-base font-semibold">Scope</legend>
				<LinkField v-model="doc.cost_center" doctype="Cost Center" label="Cost center" required :disabled="!!amendOf" :filters="{ company: session.company, disabled: 0 }" description="A group cost center covers all of its children" />
				<FormControl v-model="doc.fiscal_year" type="select" label="Fiscal year" :options="session.fiscalYears.map((f) => f.name)" required :disabled="!!amendOf" />
				<FormControl v-model="doc.budget_period" type="select" label="Budget period" :options="['Annual', 'Monthly']" description="Monthly limits each month to its share of the annual amount" />
				<FormControl v-model="doc.action_if_exceeded" type="select" label="When exceeded" :options="['Warn', 'Stop', 'Ignore']" description="Checked whenever an expense is posted" />
			</fieldset>

			<fieldset class="card p-4">
				<legend class="px-1 text-base font-semibold">Expense accounts</legend>
				<div class="space-y-3">
					<div v-for="(row, i) in doc.accounts" :key="row.key" class="grid items-end gap-2" :class="amendOf ? 'grid-cols-[minmax(0,1fr)_7rem_9rem_auto]' : 'grid-cols-[minmax(0,1fr)_9rem_auto]'">
						<LinkField v-model="row.account" doctype="Account" :label="i === 0 ? 'Account' : undefined" :filters="{ company: session.company, is_group: 0, root_type: 'Expense' }" />
						<div v-if="amendOf" class="pb-1.5 text-right text-sm tabular-nums text-ink-gray-5">
							<span v-if="i === 0" class="mb-1.5 block text-xs">Current</span>
							{{ previous[row.account] != null ? fmt(previous[row.account]) : "new" }}
						</div>
						<div>
							<FormControl v-model="row.budget_amount" type="number" min="0" step="0.01" :label="i === 0 ? 'Annual amount' : undefined" />
							<p v-if="held[row.account]" class="mt-1 text-xs" :class="Number(row.budget_amount || 0) < held[row.account] ? 'text-ink-red-4' : 'text-ink-gray-5'">
								Projects hold {{ fmt(held[row.account]) }}
							</p>
						</div>
						<Button variant="ghost" icon="lucide-trash-2" :aria-label="`Remove row ${i + 1}`" :disabled="doc.accounts.length === 1" @click="doc.accounts.splice(i, 1)" />
					</div>
				</div>
				<div class="mt-3 flex flex-wrap items-center justify-between gap-2">
					<Button variant="subtle" icon-left="lucide-plus" label="Add account" @click="addRow" />
					<span class="text-sm text-ink-gray-6">
						Total <b class="tabular-nums text-ink-gray-9">{{ fmt(total) }}</b>
						<template v-if="amendOf"> · {{ netChange }} vs current</template>
						<template v-if="heldTotal"> · <span :class="total < heldTotal ? 'text-ink-red-4' : ''">projects hold {{ fmt(heldTotal) }}</span></template>
					</span>
				</div>
			</fieldset>

			<fieldset v-if="doc.budget_period === 'Monthly'" class="card p-4">
				<legend class="px-1 text-base font-semibold">Monthly split</legend>
				<div v-if="!doc.monthly_distribution.length" class="flex flex-wrap items-center justify-between gap-2">
					<p class="text-sm text-ink-gray-6">Each month gets an even share of the annual amount.</p>
					<Button label="Set my own split" :disabled="!months.length" @click="splitEvenly" />
				</div>
				<template v-else>
					<div class="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
						<FormControl v-for="row in doc.monthly_distribution" :key="row.period_name" v-model="row.percentage" type="number" min="0" step="0.01" :label="`${row.period_name} %`" />
					</div>
					<div class="mt-3 flex flex-wrap items-center justify-between gap-2">
						<Button variant="subtle" label="Split evenly" @click="splitEvenly" />
						<span class="text-sm" :class="splitOff ? 'text-ink-red-4' : 'text-ink-gray-6'">Total {{ splitTotal.toFixed(2) }}% {{ splitOff ? "· must be 100%" : "" }}</span>
					</div>
				</template>
			</fieldset>
		</form>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { Button, FormControl, LoadingText, toast } from "frappe-ui"
import LinkField from "@/components/LinkField.vue"
import PageHeader from "@/components/PageHeader.vue"
import { getAmendment, getBudgetAllocation, insertDoc } from "@/api"
import { money } from "@/format"
import { can, currency, needsApproval, session, submitOrSend } from "@/store"

interface Period {
	period_name: string
	from_date: string
	to_date: string
	percentage: number | string
}

const route = useRoute()
const router = useRouter()
const amendOf = (route.query.amend as string) || ""
const back = amendOf ? { to: `/budgets/${amendOf}`, label: amendOf } : { to: "/budgets", label: "Budgets" }
const saving = ref(false)
const loading = ref(!!amendOf)
const previous = ref<Record<string, number>>({})
// what projects on the cancelled budget hold; the amendment must keep at least this
const held = ref<Record<string, number>>({})
const heldTotal = ref(0)
let nextKey = 1
const fmt = (v: number) => money(v, currency.value)

const doc = reactive({
	cost_center: "",
	fiscal_year: session.currentFiscalYear || session.fiscalYears[0]?.name || "",
	budget_period: "Annual",
	action_if_exceeded: "Warn",
	amendment_reason: "",
	accounts: [{ key: 0, account: "", budget_amount: "" as number | string }],
	monthly_distribution: [] as Period[],
})

const total = computed(() => doc.accounts.reduce((t, r) => t + Number(r.budget_amount || 0), 0))
const netChange = computed(() => {
	const change = total.value - Object.values(previous.value).reduce((t, v) => t + v, 0)
	return change ? `${change > 0 ? "+" : "−"}${fmt(Math.abs(change))}` : "no change"
})
const splitTotal = computed(() => doc.monthly_distribution.reduce((t, r) => t + Number(r.percentage || 0), 0))
const splitOff = computed(() => Math.abs(splitTotal.value - 100) > 0.01)

const months = computed(() => {
	const year = session.fiscalYears.find((f) => f.name === doc.fiscal_year)
	if (!year) return []
	const out: Omit<Period, "percentage">[] = []
	const end = year.end_date
	let [y, m, d] = year.start_date.split("-").map(Number)
	for (;;) {
		const from = iso(y, m, d)
		if (from > end) break
		const lastDay = iso(y, m, new Date(Date.UTC(y, m, 0)).getUTCDate())
		const to = lastDay < end ? lastDay : end
		out.push({ period_name: new Date(Date.UTC(y, m - 1, 1)).toLocaleString("en", { month: "short", year: "numeric", timeZone: "UTC" }), from_date: from, to_date: to })
		;[y, m, d] = m === 12 ? [y + 1, 1, 1] : [y, m + 1, 1]
	}
	return out
})

function iso(y: number, m: number, d: number) {
	return `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`
}

function splitEvenly() {
	const share = Math.floor((100 / months.value.length) * 1e6) / 1e6
	doc.monthly_distribution = months.value.map((p, i) => ({
		...p,
		percentage: i < months.value.length - 1 ? share : Number((100 - share * (months.value.length - 1)).toFixed(6)),
	}))
}

// a custom split belongs to one fiscal year (an amendment keeps its year)
watch(
	() => doc.fiscal_year,
	() => {
		if (!amendOf) doc.monthly_distribution = []
	},
)

function addRow() {
	doc.accounts.push({ key: nextKey++, account: "", budget_amount: "" })
}

async function loadAmendment() {
	const result = await getAmendment<any>("Budget", amendOf)
	if (result.existing) {
		toast.info(`${amendOf} already has an open amendment`)
		router.replace(`/budgets/${result.existing}`)
		return
	}
	const copy = result.doc
	Object.assign(doc, {
		cost_center: copy.cost_center,
		fiscal_year: copy.fiscal_year,
		budget_period: copy.budget_period,
		action_if_exceeded: copy.action_if_exceeded,
		accounts: copy.accounts.map((r: any) => ({ key: nextKey++, account: r.account, budget_amount: r.budget_amount })),
	})
	previous.value = Object.fromEntries(copy.accounts.map((r: any) => [r.account, r.budget_amount]))
	const allocation = await getBudgetAllocation(amendOf)
	held.value = Object.fromEntries(allocation.accounts.filter((r) => r.held).map((r) => [r.account, r.held]))
	heldTotal.value = allocation.held
	doc.monthly_distribution = copy.monthly_distribution.map((r: any) => ({ period_name: r.period_name, from_date: r.from_date, to_date: r.to_date, percentage: r.percentage }))
	loading.value = false
}

async function save(submit: boolean) {
	saving.value = true
	try {
		const saved = await insertDoc<{ name: string }>({
			doctype: "Budget",
			company: session.company,
			cost_center: doc.cost_center,
			fiscal_year: doc.fiscal_year,
			budget_period: doc.budget_period,
			action_if_exceeded: doc.action_if_exceeded,
			accounts: doc.accounts.filter((r) => r.account).map((r) => ({ account: r.account, budget_amount: Number(r.budget_amount) })),
			monthly_distribution: doc.budget_period === "Monthly" ? doc.monthly_distribution.map((r) => ({ ...r, percentage: Number(r.percentage || 0) })) : [],
			...(amendOf ? { amended_from: amendOf, amendment_reason: doc.amendment_reason } : {}),
		})
		const sent = submit && (await submitOrSend("Budget", saved.name))
		toast.success(sent ? `${saved.name} sent for approval` : submit ? `${saved.name} submitted` : "Draft saved")
		router.replace(`/budgets/${saved.name}`)
	} finally {
		saving.value = false
	}
}

onMounted(() => {
	if (amendOf) loadAmendment()
})
</script>
