<template>
	<div v-if="!budget" class="p-6"><LoadingText /></div>
	<div v-else>
		<PageHeader :title="budget.cost_center" :subtitle="`${budget.name} · ${budget.fiscal_year} · ${budget.budget_period}`" :back="{ to: '/budgets', label: 'Budgets' }">
			<template #badge>
				<StatusBadge :status="budget.docstatus === 0 ? 'Draft' : budget.docstatus === 2 ? 'Cancelled' : summaryStatus" />
			</template>
			<template #actions>
				<Button v-if="deskAccess" label="Open in Desk" icon-left="lucide-external-link" @click="openDesk" />
				<Button v-if="budget.docstatus === 0 && can('Budget', 'submit') && !needsApproval('Budget')" variant="solid" label="Submit" :loading="busy" @click="submit" />
				<template v-if="budget.docstatus === 1 && canCancel">
					<Button theme="red" label="Cancel" :loading="busy" @click="cancel(false)" />
					<Button variant="solid" label="Cancel & Amend" icon-left="lucide-pencil" :loading="busy" @click="cancel(true)" />
				</template>
				<Button v-if="budget.docstatus === 2 && !amendedAs && can('Budget', 'create')" variant="solid" label="Amend" icon-left="lucide-pencil" @click="amend" />
			</template>
		</PageHeader>

		<DocLayout doctype="Budget" :name="name" :version="budget.modified">
			<div class="space-y-6">
				<VersionsCard :name="name" base="budgets" :versions="versions" :currency="budget.currency" />
				<ApprovalBar doctype="Budget" :name="name" @changed="load" />
				<div v-if="summary" class="grid grid-cols-2 gap-3 lg:grid-cols-4">
					<StatCard label="Allocated" :value="fmt(summary.allocated)" />
					<StatCard label="Spent" :value="fmt(summary.actual)" />
					<StatCard label="Remaining" :value="fmt(summary.remaining)" :tone="summary.remaining < 0 ? 'red' : undefined" />
					<StatCard label="Utilization" :value="percent(summary.utilization)" :tone="utilizationTone(summary.utilization)" :hint="`On exceed: ${budget.action_if_exceeded}`" />
				</div>
				<p v-else class="rounded-lg bg-surface-gray-1 p-3 text-sm text-ink-gray-6">Actual spending is tracked once the budget is submitted.</p>

				<section class="card">
					<h2 class="px-4 pt-4 text-base font-semibold sm:px-6">By account</h2>
					<DataTable class="mt-2" row-key="account" :columns="accountColumns" :rows="accountRows">
						<template #utilization="{ row }"><div class="w-40"><UsageBar :value="row.utilization" :caption="percent(row.utilization)" /></div></template>
					</DataTable>
				</section>

				<p v-if="allocation && (allocation.projects.length || allocation.recurring.length)" class="text-sm text-ink-gray-6">
					Projects and recurring payments hold {{ fmt(allocation.held) }} of {{ fmt(allocation.total) }} · {{ fmt(allocation.free) }} free
				</p>

				<section v-if="allocation?.projects.length" class="card">
					<h2 class="px-4 pt-4 text-base font-semibold sm:px-6">Projects</h2>
					<DataTable class="mt-2" :columns="projectColumns" :rows="allocation.projects" clickable @row-click="(r) => $router.push(`/projects/${r.name}`)">
						<template #project_name="{ row }">
							<div class="font-medium text-ink-gray-9">{{ row.project_name }}</div>
							<div class="text-sm text-ink-gray-5">{{ row.name }}</div>
						</template>
						<template #status="{ value }"><StatusBadge :status="value" /></template>
					</DataTable>
				</section>

				<section v-if="allocation?.recurring.length" class="card">
					<div class="flex flex-wrap items-baseline justify-between gap-2 px-4 pt-4 sm:px-6">
						<h2 class="text-base font-semibold">Recurring payments</h2>
						<span class="text-sm text-ink-gray-6">
							{{ fmt(allocation.recurring_held) }} held · {{ fmt(allocation.recurring_paid) }} paid · <b class="text-ink-gray-9">{{ fmt(allocation.recurring_remaining) }}</b> still to pay
						</span>
					</div>
					<p v-if="allocation.recurring.some((r) => !r.counted)" class="px-4 pt-1 text-xs text-ink-gray-5 sm:px-6">Those of a project with a share take from it</p>
					<DataTable class="mt-2" :columns="recurringColumns" :rows="allocation.recurring" clickable @row-click="(r) => $router.push(`/recurring/${r.name}`)">
						<template #title="{ row }">
							<div class="font-medium text-ink-gray-9">{{ row.title.replace(`${row.name} `, "") }}</div>
							<div class="text-sm text-ink-gray-5">{{ row.name }}</div>
						</template>
						<template #project="{ row }">
							<RouterLink v-if="row.project" :to="`/projects/${row.project}`" class="hover:underline" @click.stop>{{ row.project_name || row.project }}</RouterLink>
							<span v-else class="text-ink-gray-5">—</span>
						</template>
						<template #status="{ value }"><StatusBadge :status="value" /></template>
						<template #remaining="{ value }"><span :class="value > 0 ? 'text-ink-amber-4' : 'text-ink-gray-5'">{{ fmt(value) }}</span></template>
					</DataTable>
				</section>

				<section v-if="summary" class="card p-4 sm:p-6">
					<h2 class="mb-4 text-base font-semibold">Month by month</h2>
					<BarChart :labels="months.labels" :series="months.series" :format="fmt" />
				</section>
			</div>
		</DocLayout>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { Button, dialog, LoadingText, toast } from "frappe-ui"
import { useRouter } from "vue-router"
import ApprovalBar from "@/components/ApprovalBar.vue"
import BarChart from "@/components/BarChart.vue"
import DataTable, { type Column } from "@/components/DataTable.vue"
import DocLayout from "@/components/DocLayout.vue"
import PageHeader from "@/components/PageHeader.vue"
import StatCard from "@/components/StatCard.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import UsageBar from "@/components/UsageBar.vue"
import VersionsCard from "@/components/VersionsCard.vue"
import { api, type BudgetAllocation, cancelDoc, getBudgetAllocation, getDoc, getVersions, submitDoc, type Version } from "@/api"
import { money, percent, utilizationTone } from "@/format"
import { can, currency, deskAccess, hasRole, needsApproval } from "@/store"

const props = defineProps<{ name: string }>()

const router = useRouter()
const budget = ref<any>(null)
const summary = ref<any>(null)
const versions = ref<Version[]>([])
const allocation = ref<BudgetAllocation | null>(null)
const busy = ref(false)
const canCancel = computed(() => hasRole("Accounts Manager") || hasRole("General Manager"))
const amendedAs = computed(() => versions.value[versions.value.findIndex((v) => v.name === props.name) + 1])
// a project that holds the budget alone takes the approved amendment as its share
const soleProject = computed(() => {
	const held = allocation.value
	const project = held?.projects.length === 1 ? held.projects[0] : null
	if (!project || held!.recurring.some((r) => r.counted)) return null
	return project.budget_amount || Object.keys(project.accounts).length ? project : null
})
const fmt = (v: number) => money(v, budget.value?.currency || currency.value)

const summaryStatus = computed(() => {
	const u = summary.value?.utilization || 0
	return u > 100 ? "Exceeded" : u >= 80 ? "Near Limit" : "On Track"
})

const accountColumns = computed<Column[]>(() => [
	{ key: "account", label: "Account" },
	{ key: "budget", label: "Allocated", align: "right", format: (v) => fmt(v) },
	...(summary.value
		? ([
				{ key: "actual", label: "Spent", align: "right", format: (v: number) => fmt(v) },
				{ key: "remaining", label: "Remaining", align: "right", format: (v: number) => fmt(v) },
				{ key: "utilization", label: "Utilization" },
			] as Column[])
		: []),
])

const projectColumns: Column[] = [
	{ key: "project_name", label: "Project" },
	{ key: "status", label: "Status" },
	{ key: "budget_amount", label: "Share", align: "right", format: (v) => (v ? fmt(v) : "No total") },
	{ key: "spent", label: "Spent", align: "right", format: (v) => fmt(v) },
]

const recurringColumns: Column[] = [
	{ key: "title", label: "Recurring payment" },
	{ key: "project", label: "Project" },
	{ key: "account", label: "Account" },
	{ key: "status", label: "Status" },
	{ key: "budget_amount", label: "Holds", align: "right", format: (v) => fmt(v) },
	{ key: "paid", label: "Paid", align: "right", format: (v) => fmt(v) },
	{ key: "remaining", label: "Remaining", align: "right" },
]

const accountRows = computed(() =>
	summary.value ? summary.value.rows : budget.value.accounts.map((a: any) => ({ account: a.account, budget: a.budget_amount })),
)

const months = computed(() => {
	const byPeriod = new Map<string, { budget: number; actual: number }>()
	for (const p of summary.value?.periods || []) {
		const entry = byPeriod.get(p.period) || { budget: 0, actual: 0 }
		entry.budget += p.budget
		entry.actual += p.actual
		byPeriod.set(p.period, entry)
	}
	const labels = [...byPeriod.keys()]
	return {
		labels: labels.map((l) => l.split(" ")[0]),
		series: [
			{ name: "Budget", values: labels.map((l) => byPeriod.get(l)!.budget) },
			{ name: "Actual", values: labels.map((l) => byPeriod.get(l)!.actual) },
		],
	}
})

async function load() {
	const [doc, chain, held] = await Promise.all([getDoc("Budget", props.name), getVersions("Budget", props.name), getBudgetAllocation(props.name)])
	versions.value = chain
	allocation.value = held
	summary.value = doc.docstatus === 1 ? await api("spend.budgeting.doctype.budget.budget.get_budget_summary", { budget: props.name }) : null
	budget.value = doc
}

function amend() {
	router.push({ path: "/budgets/new", query: { amend: props.name } })
}

function cancel(thenAmend: boolean) {
	dialog.confirm({
		title: thenAmend ? "Cancel and amend this budget?" : "Cancel this budget?",
		message: `${budget.value.cost_center} has no budget until ${thenAmend ? "the amendment" : "a new budget"} is approved, so expenses are not checked in the meantime.${allocation.value?.projects.length || allocation.value?.recurring.length ? ` Its projects and recurring payments keep what they hold and move to the amendment when it is approved.${soleProject.value ? ` The project's share then becomes the amendment's amounts.` : ""}` : ""}`,
		confirmLabel: thenAmend ? "Cancel & Amend" : "Cancel Budget",
		theme: "red",
		onConfirm: async () => {
			busy.value = true
			try {
				await cancelDoc("Budget", props.name)
				toast.success(`${props.name} cancelled`)
				if (thenAmend) amend()
				else await load()
			} finally {
				busy.value = false
			}
		},
	})
}

function submit() {
	dialog.confirm({
		title: "Submit budget?",
		message: "Expenses posted against this cost center will be checked against it.",
		confirmLabel: "Submit",
		onConfirm: async () => {
			busy.value = true
			try {
				await submitDoc("Budget", props.name)
				toast.success("Budget submitted")
				await load()
			} finally {
				busy.value = false
			}
		},
	})
}

function openDesk() {
	window.open(`/app/budget/${props.name}`, "_blank")
}

onMounted(load)
watch(() => props.name, load)
</script>
