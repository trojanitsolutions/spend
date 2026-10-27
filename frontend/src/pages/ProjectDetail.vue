<template>
	<div v-if="!detail" class="p-6"><LoadingText /></div>
	<div v-else>
		<PageHeader :title="project.project_name" :subtitle="subtitle" :back="{ to: '/projects', label: 'Projects' }">
			<template #badge><StatusBadge :status="project.status" /></template>
			<template #actions>
				<Button label="Open in Desk" icon-left="lucide-external-link" @click="openDesk" />
				<template v-if="detail.can_write">
					<Button
						v-if="project.status === 'Open'"
						label="Mark Completed"
						:loading="busy"
						:disabled="detail.open_tasks > 0"
						:tooltip="detail.open_tasks > 0 ? `${detail.open_tasks} task${detail.open_tasks === 1 ? ' is' : 's are'} still open` : undefined"
						@click="setStatus('Completed')"
					/>
					<Button v-else label="Reopen" :loading="busy" @click="setStatus('Open')" />
				</template>
				<Button
					v-if="project.status === 'Open' && usable && can('Journal Entry', 'create')"
					icon-left="lucide-receipt"
					label="Book Expense"
					@click="$router.push({ path: '/expenses/new', query: { project: project.name } })"
				/>
				<Button
					v-if="project.status === 'Open' && usable && can('Purchase Invoice', 'create')"
					variant="solid"
					icon-left="lucide-plus"
					label="New Bill"
					@click="$router.push({ path: '/bills/new', query: { project: project.name } })"
				/>
			</template>
		</PageHeader>

		<div class="space-y-6 p-4 sm:p-6">
			<ApprovalBar doctype="Project" :name="name" @changed="load" />
			<div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
				<StatCard label="Budget" :value="project.budget_amount ? fmt(project.budget_amount) : 'No limit'" :hint="project.budget ? `Share of ${project.budget} · ${project.action_if_exceeded} when exceeded` : `${project.action_if_exceeded} when exceeded`" />
				<StatCard label="Spent" :value="fmt(detail.spent)" :hint="detail.utilization !== null ? `${percent(detail.utilization)} of budget` : 'Expenses booked to the project'" />
				<StatCard
					label="Remaining"
					:value="detail.remaining === null ? '—' : fmt(detail.remaining)"
					:tone="detail.remaining !== null && detail.remaining < 0 ? 'red' : undefined"
				/>
				<StatCard label="Owed to suppliers" :value="fmt(detail.outstanding)" :hint="`${fmt(detail.paid)} paid of ${fmt(detail.billed)} billed`" />
			</div>

			<section v-if="detail.utilization !== null" class="rounded-xl border border-outline-gray-1 p-4">
				<UsageBar :value="detail.utilization" label="Budget used" :caption="`${fmt(detail.spent)} / ${fmt(project.budget_amount)}`" />
			</section>

			<section v-if="detail.tasks.length || canAddTask" class="rounded-xl border border-outline-gray-1">
				<div class="flex flex-wrap items-center justify-between gap-2 px-4 pt-4 sm:px-6">
					<div>
						<h2 class="text-base font-semibold">Tasks</h2>
						<p class="text-sm text-ink-gray-5">
							<template v-if="detail.tasks.length">{{ detail.tasks.length - detail.open_tasks }} of {{ detail.tasks.length }} done · the project can be completed when every task is completed or cancelled</template>
							<template v-else>Add tasks to track the work. The project can be completed when all are done.</template>
						</p>
					</div>
					<div class="flex items-center gap-3">
						<div v-if="detail.tasks.length" class="w-36"><UsageBar :value="project.percent_complete || 0" :caption="percent(project.percent_complete || 0)" /></div>
						<Button v-if="canAddTask" variant="ghost" icon-left="lucide-plus" label="New Task" @click="openTask()" />
					</div>
				</div>
				<TreeTable
					v-if="detail.tasks.length"
					class="mt-2"
					:rows="taskRows"
					name-field="name"
					name-label="Task"
					parent-field="parent_task"
					:collapsed="collapsedTasks"
					:label="(r) => r.subject"
					:columns="taskColumns"
					clickable
					@row-click="(r: any) => openTask(r.name)"
					@toggle="toggleTask"
				>
					<template #status="{ value }"><StatusBadge :status="value" /></template>
					<template #actions="{ row }">
						<Button
							v-if="can('Task', 'write') && !['Completed', 'Cancelled'].includes(row.status) && !row.is_group"
							size="sm"
							variant="ghost"
							icon-left="lucide-check"
							label="Done"
							@click.stop="completeTask(row.name)"
						/>
					</template>
				</TreeTable>
				<div v-else class="h-4" />
				<CompleteTaskDialog v-model:open="completeOpen" :tasks="completing" @done="load" />
			</section>

			<section v-if="detail.accounts.length" class="rounded-xl border border-outline-gray-1">
				<h2 class="px-4 pt-4 text-base font-semibold sm:px-6">Account limits</h2>
				<DataTable class="mt-2" row-key="account" :columns="accountColumns" :rows="detail.accounts">
					<template #account="{ row }">
						<span class="tabular-nums text-ink-gray-5">{{ row.account_number }}</span>
						<span class="ml-1">{{ row.account }}</span>
					</template>
					<template #utilization="{ value }"><div class="w-36"><UsageBar :value="value" :caption="percent(value)" /></div></template>
					<template #remaining="{ value }"><span :class="value < 0 ? 'text-ink-red-4' : ''">{{ fmt(value) }}</span></template>
				</DataTable>
			</section>

			<section v-if="detail.categories.length" class="rounded-xl border border-outline-gray-1">
				<h2 class="px-4 pt-4 text-base font-semibold sm:px-6">Expense categories</h2>
				<DataTable class="mt-2" :row-key="'key'" :columns="categoryColumns" :rows="categoryRows">
					<template #category="{ row }">
						<span class="text-ink-gray-9">{{ row.category }}</span>
						<span v-if="row.sub_category" class="text-ink-gray-6"> / {{ row.sub_category }}</span>
					</template>
					<template #utilization="{ value }">
						<div v-if="value !== null" class="w-36"><UsageBar :value="value" :caption="percent(value)" /></div>
						<span v-else class="text-ink-gray-5">No limit</span>
					</template>
					<template #remaining="{ value }"><span :class="value !== null && value < 0 ? 'text-ink-red-4' : ''">{{ value === null ? "—" : fmt(value) }}</span></template>
				</DataTable>
			</section>

			<section v-if="detail.monthly.rows.length" class="rounded-xl border border-outline-gray-1">
				<div class="flex items-center justify-between px-4 pt-4 sm:px-6">
					<h2 class="text-base font-semibold">Charged each month by category</h2>
					<Button variant="ghost" icon-left="lucide-chart-column" label="Full report" @click="$router.push({ path: '/reports/project-category-monthly', query: { project: project.name } })" />
				</div>
				<div class="mt-2 overflow-x-auto">
					<table class="w-full text-sm">
						<thead>
							<tr class="border-b border-outline-gray-1 text-left text-ink-gray-5">
								<th class="sticky left-0 bg-surface-white px-4 py-2 font-normal sm:px-6">Category</th>
								<th v-for="month in detail.monthly.months" :key="month" class="whitespace-nowrap px-3 py-2 text-right font-normal">{{ monthLabel(month) }}</th>
								<th class="px-4 py-2 text-right font-normal sm:pr-6">Total</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="row in detail.monthly.rows" :key="`${row.category}|${row.sub_category || ''}`" class="border-b border-outline-gray-1 last:border-0">
								<td class="sticky left-0 whitespace-nowrap bg-surface-white px-4 py-2 sm:px-6" :class="row.indent ? 'pl-8 text-ink-gray-6 sm:pl-10' : 'font-medium text-ink-gray-9'">
									{{ row.sub_category || row.category }}
								</td>
								<td v-for="month in detail.monthly.months" :key="month" class="px-3 py-2 text-right tabular-nums" :class="row.months[month] ? 'text-ink-gray-8' : 'text-ink-gray-4'">
									{{ row.months[month] ? fmt(row.months[month]) : "—" }}
								</td>
								<td class="px-4 py-2 text-right font-medium tabular-nums text-ink-gray-9 sm:pr-6">{{ fmt(row.total) }}</td>
							</tr>
						</tbody>
					</table>
				</div>
			</section>

			<section class="rounded-xl border border-outline-gray-1">
				<h2 class="px-4 pt-4 text-base font-semibold sm:px-6">Bills</h2>
				<DataTable class="mt-2" :columns="billColumns" :rows="detail.bills" clickable empty-text="No bills for this project yet" @row-click="(r) => $router.push(`/bills/${r.name}`)">
					<template #supplier="{ row }">
						<div class="font-medium text-ink-gray-9">{{ row.supplier }}</div>
						<div class="text-sm text-ink-gray-5">{{ row.name }}<template v-if="row.bill_no"> · {{ row.bill_no }}</template></div>
					</template>
					<template #status="{ value }"><StatusBadge :status="value" /></template>
				</DataTable>
			</section>

			<section v-if="detail.recurring.length || can('Recurring Payment', 'create')" class="rounded-xl border border-outline-gray-1">
				<div class="flex items-center justify-between px-4 pt-4 sm:px-6">
					<h2 class="text-base font-semibold">Recurring payments</h2>
					<Button
						v-if="project.status === 'Open' && can('Recurring Payment', 'create')"
						variant="ghost"
						icon-left="lucide-plus"
						label="New"
						@click="$router.push({ path: '/recurring/new', query: { project: project.name } })"
					/>
				</div>
				<DataTable class="mt-2" :columns="recurringColumns" :rows="detail.recurring" clickable empty-text="No recurring payments for this project" @row-click="(r) => $router.push(`/recurring/${r.name}`)">
					<template #title="{ row }">
						<div class="font-medium text-ink-gray-9">{{ row.title }}</div>
						<div class="text-sm text-ink-gray-5">{{ row.name }} · {{ row.frequency }}</div>
					</template>
					<template #status="{ value }"><StatusBadge :status="value" /></template>
				</DataTable>
			</section>

			<div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
				<section class="rounded-xl border border-outline-gray-1 p-4">
					<h2 class="mb-3 text-base font-semibold">Details</h2>
					<dl class="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
						<template v-for="[label, value] in details" :key="label">
							<dt class="text-ink-gray-5">{{ label }}</dt>
							<dd class="whitespace-pre-line break-words text-right text-ink-gray-8">
								<RouterLink v-if="label === 'Budget' && value" :to="`/budgets/${value}`" class="hover:underline">{{ value }}</RouterLink>
								<template v-else>{{ value || "—" }}</template>
							</dd>
						</template>
					</dl>
				</section>
				<section class="rounded-xl border border-outline-gray-1 lg:col-span-2">
					<h2 class="px-4 pt-4 text-base font-semibold sm:px-6">Payments</h2>
					<DataTable class="mt-2" :columns="paymentColumns" :rows="detail.payments" empty-text="No payments tagged with this project">
						<template #name="{ value }"><a :href="`/app/supplier-payment/${value}`" class="hover:underline">{{ value }}</a></template>
						<template #docstatus="{ value }"><StatusBadge :status="docstatusLabel(value)" /></template>
					</DataTable>
				</section>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import { Button, LoadingText, toast } from "frappe-ui"
import ApprovalBar from "@/components/ApprovalBar.vue"
import CompleteTaskDialog from "@/components/CompleteTaskDialog.vue"
import DataTable, { type Column } from "@/components/DataTable.vue"
import PageHeader from "@/components/PageHeader.vue"
import StatCard from "@/components/StatCard.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import TreeTable from "@/components/TreeTable.vue"
import UsageBar from "@/components/UsageBar.vue"
import { api } from "@/api"
import { date, docstatusLabel, money, percent } from "@/format"
import { can, currency, needsApproval } from "@/store"

const props = defineProps<{ name: string }>()

const router = useRouter()

const detail = ref<any>(null)
const busy = ref(false)
const project = computed(() => detail.value.doc)
const fmt = (v: number) => money(v, project.value?.currency || currency.value)
const usable = computed(() => !needsApproval("Project") || project.value.workflow_state === "Approved")

const subtitle = computed(() => {
	const range = [project.value.start_date, project.value.end_date].filter(Boolean).map(date).join(" – ")
	return [project.value.name, range].filter(Boolean).join(" · ")
})

const collapsedTasks = ref(new Set<string>())
const canAddTask = computed(() => project.value.status === "Open" && can("Task", "create"))
const taskColumns: Column[] = [
	{ key: "status", label: "Status" },
	{ key: "priority", label: "Priority" },
	{ key: "exp_end_date", label: "Due", format: (v) => (v ? date(v) : "—") },
	{ key: "progress", label: "Progress", align: "right", format: (v) => percent(v || 0, 0) },
	{ key: "_assign", label: "Assigned", format: (v) => JSON.parse(v || "[]").join(", ") || "—" },
	{ key: "actions", label: "" },
]

// depth of each task from its parent chain; rows come in tree order
const taskRows = computed(() => {
	const depth: Record<string, number> = {}
	return detail.value.tasks.map((t: any) => {
		depth[t.name] = t.parent_task ? (depth[t.parent_task] ?? 0) + 1 : 0
		return { ...t, indent: depth[t.name] }
	})
})

function toggleTask(name: string) {
	const next = new Set(collapsedTasks.value)
	next.has(name) ? next.delete(name) : next.add(name)
	collapsedTasks.value = next
}

function openTask(name?: string) {
	router.push(name ? { path: `/tasks/${name}`, query: { from: "project" } } : { path: "/tasks/new", query: { project: props.name } })
}

const completing = ref<string[]>([])
const completeOpen = ref(false)

function completeTask(name: string) {
	completing.value = [name]
	completeOpen.value = true
}

const accountColumns: Column[] = [
	{ key: "account", label: "Expense Account" },
	{ key: "budget", label: "Share", align: "right", format: (v) => fmt(v) },
	{ key: "actual", label: "Spent", align: "right", format: (v) => fmt(v) },
	{ key: "remaining", label: "Remaining", align: "right" },
	{ key: "utilization", label: "Used" },
]

const categoryColumns: Column[] = [
	{ key: "category", label: "Category" },
	{ key: "budget", label: "Budget", align: "right", format: (v) => (v ? fmt(v) : "—") },
	{ key: "charged", label: "Charged", align: "right", format: (v) => fmt(v) },
	{ key: "remaining", label: "Remaining", align: "right" },
	{ key: "utilization", label: "Used" },
]
const categoryRows = computed(() => detail.value.categories.map((r: any) => ({ ...r, key: `${r.category}|${r.sub_category || ""}` })))

function monthLabel(month: string) {
	return new Date(`${month}-01T00:00:00`).toLocaleDateString(undefined, { month: "short", year: "numeric" })
}

const billColumns: Column[] = [
	{ key: "supplier", label: "Supplier" },
	{ key: "posting_date", label: "Date", format: date },
	{ key: "due_date", label: "Due", format: date },
	{ key: "status", label: "Status" },
	{ key: "grand_total", label: "Total", align: "right", format: (v) => fmt(v) },
	{ key: "outstanding_amount", label: "Outstanding", align: "right", format: (v) => fmt(v) },
]

const paymentColumns: Column[] = [
	{ key: "posting_date", label: "Date", format: date },
	{ key: "name", label: "Payment" },
	{ key: "supplier", label: "Supplier" },
	{ key: "mode_of_payment", label: "Mode" },
	{ key: "docstatus", label: "Status" },
	{ key: "paid_amount", label: "Amount", align: "right", format: (v) => fmt(v) },
]

const recurringColumns: Column[] = [
	{ key: "title", label: "Payment" },
	{ key: "next_date", label: "Next", format: (v) => (v ? date(v) : "—") },
	{ key: "status", label: "Status" },
	{ key: "paid_amount", label: "Paid", align: "right", format: (v) => fmt(v) },
	{ key: "total_amount", label: "Total", align: "right", format: (v) => fmt(v) },
]

const details = computed(() => [
	["Budget", project.value.budget],
	["Default cost center", project.value.cost_center],
	["Start date", date(project.value.start_date)],
	["End date", date(project.value.end_date)],
	["Description", project.value.description],
])

async function load() {
	detail.value = await api("spend.spend.doctype.project.project.get_project_summary", { project: props.name })
}

async function setStatus(status: string) {
	busy.value = true
	try {
		await api("frappe.client.set_value", { doctype: "Project", name: props.name, fieldname: "status", value: status })
		toast.success(status === "Open" ? "Project reopened" : "Project marked completed")
		await load()
	} finally {
		busy.value = false
	}
}

function openDesk() {
	window.open(`/app/project/${props.name}`, "_blank")
}

onMounted(load)
</script>
