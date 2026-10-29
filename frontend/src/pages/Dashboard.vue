<template>
	<div>
		<PageHeader title="Dashboard" :subtitle="data?.fiscal_year ? `${session.company} · ${data.fiscal_year}` : session.company">
			<template #actions>
				<Button v-if="can('Purchase Invoice', 'create')" icon-left="lucide-plus" label="New Bill" @click="$router.push('/bills/new')" />
				<Button v-if="can('Journal Entry', 'create')" icon-left="lucide-plus" label="Record Expense" @click="$router.push('/expenses/new')" />
				<Button v-if="can('Asset', 'create')" variant="solid" icon-left="lucide-plus" label="New Asset" @click="$router.push('/assets/new')" />
			</template>
		</PageHeader>

		<div v-if="!data" class="p-6"><LoadingText /></div>
		<div v-else class="space-y-6 p-4 sm:p-6">
			<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
				<template v-if="data.budget">
					<StatCard icon="lucide-wallet" label="Spent this year" :value="fmt(data.budget.actual)">
						<template v-if="data.budget.allocated">of {{ fmt(data.budget.allocated) }} budgeted</template>
						<template v-else>No budgets for this year</template>
					</StatCard>
					<StatCard
						icon="lucide-gauge"
						label="Budget utilization"
						:value="percent(data.budget.utilization)"
						:tone="data.budget.allocated ? utilizationTone(data.budget.utilization) : undefined"
						:hint="data.budget.allocated ? `${fmt(data.budget.allocated - data.budget.actual)} remaining` : '—'"
					/>
				</template>
				<StatCard v-if="data.assets" icon="lucide-laptop" label="Asset book value" :value="fmt(data.assets.book_value)">
					{{ data.assets.count }} assets · {{ fmt(data.assets.accumulated) }} depreciated
				</StatCard>
				<StatCard
					v-if="data.depreciation_due"
					icon="lucide-calendar-clock"
					label="Depreciation due"
					:value="fmt(data.depreciation_due.amount)"
					:tone="data.depreciation_due.count ? 'amber' : undefined"
				>
					<span v-if="data.depreciation_due.count">
						{{ data.depreciation_due.count }} entries ·
						<button v-if="can('Journal Entry', 'submit')" class="font-medium text-ink-gray-8 underline" :disabled="posting" @click="postDue">
							{{ posting ? "Posting…" : "Post now" }}
						</button>
					</span>
					<span v-else>All caught up</span>
				</StatCard>
				<StatCard v-if="data.payables" icon="lucide-file-text" label="Owed to suppliers" :value="fmt(data.payables.outstanding)" :tone="data.payables.overdue > 0 ? 'red' : undefined">
					<RouterLink v-if="data.payables.overdue > 0" to="/bills" class="underline">
						{{ fmt(data.payables.overdue) }} overdue · {{ data.payables.overdue_count }} bills
					</RouterLink>
					<template v-else-if="data.payables.open_bills">{{ data.payables.open_bills }} open bills, none overdue</template>
					<template v-else>No open bills</template>
				</StatCard>
			</div>

			<div v-if="data.spending_trend || data.budget" class="grid grid-cols-1 gap-4 xl:grid-cols-3">
				<section v-if="data.spending_trend" class="card p-4 xl:col-span-2">
					<h2 class="mb-4 text-base font-semibold">Monthly spending</h2>
					<BarChart
						:labels="data.spending_trend.map((m: any) => m.month)"
						:series="[{ name: 'Spending', values: data.spending_trend.map((m: any) => m.amount) }]"
						:format="fmt"
					/>
				</section>

				<section v-if="data.budget" class="card p-4">
					<div class="mb-4 flex items-center justify-between">
						<h2 class="text-base font-semibold">Budgets to watch</h2>
						<RouterLink to="/budgets" class="text-sm text-ink-gray-5 hover:text-ink-gray-8">All budgets</RouterLink>
					</div>
					<div v-if="!data.budget.budgets.length" class="py-6 text-center text-sm text-ink-gray-5">No submitted budgets this year</div>
					<div v-else class="space-y-4">
						<RouterLink v-for="b in data.budget.budgets" :key="b.budget" :to="`/budgets/${b.budget}`" class="block">
							<UsageBar :value="b.utilization" :label="b.cost_center" :caption="`${fmt(b.actual)} / ${fmt(b.allocated)}`" />
						</RouterLink>
					</div>
				</section>
			</div>

			<section v-if="data.projects?.open" class="card p-4">
				<div class="mb-4 flex flex-wrap items-center justify-between gap-2">
					<h2 class="text-base font-semibold">
						Projects
						<span class="ml-2 text-sm font-normal text-ink-gray-5">
							{{ data.projects.open }} open · {{ fmt(data.projects.spent) }} spent
							<span v-if="data.projects.over_budget" class="text-ink-red-4">· {{ data.projects.over_budget }} over budget</span>
						</span>
					</h2>
					<RouterLink to="/projects" class="text-sm text-ink-gray-5 hover:text-ink-gray-8">All projects</RouterLink>
				</div>
				<div v-if="!data.projects.top.length" class="py-4 text-center text-sm text-ink-gray-5">No open project has a budget yet</div>
				<div v-else class="grid grid-cols-1 gap-x-8 gap-y-4 md:grid-cols-2">
					<RouterLink v-for="p in data.projects.top" :key="p.name" :to="`/projects/${p.name}`" class="block">
						<UsageBar :value="p.utilization" :label="p.project_name" :caption="`${fmt(p.spent)} / ${fmt(p.budget_amount)}`" />
					</RouterLink>
				</div>
			</section>

			<section v-if="data.upcoming_payments.length" class="card">
				<div class="flex items-center justify-between px-4 pt-4 sm:px-6">
					<h2 class="text-base font-semibold">Upcoming recurring payments <span class="ml-2 text-sm font-normal text-ink-gray-5">next 30 days</span></h2>
					<RouterLink to="/recurring" class="text-sm text-ink-gray-5 hover:text-ink-gray-8">All recurring</RouterLink>
				</div>
				<DataTable
					class="mt-2"
					row-key="key"
					clickable
					:columns="[
						{ key: 'payment_date', label: 'Date', format: (v: string) => date(v) },
						{ key: 'title', label: 'Payment' },
						{ key: 'project', label: 'Project', format: (v: string) => v || '—' },
						{ key: 'amount', label: 'Amount', align: 'right', format: (v: number) => fmt(v) },
					]"
					:rows="data.upcoming_payments.map((r: any) => ({ ...r, key: `${r.name}-${r.payment_date}` }))"
					@row-click="(r: any) => $router.push(`/recurring/${r.name}`)"
				>
					<template #payment_date="{ value }"><span :class="value <= today() ? 'text-ink-amber-3' : ''">{{ date(value) }}</span></template>
				</DataTable>
			</section>

			<div v-if="data.top_cost_centers || data.recent_entries" class="grid grid-cols-1 gap-4 xl:grid-cols-2">
				<section v-if="data.top_cost_centers" class="card">
					<div class="flex items-center justify-between px-4 pt-4 sm:px-6">
						<h2 class="text-base font-semibold">Top cost centers</h2>
						<RouterLink to="/cost-centers" class="text-sm text-ink-gray-5 hover:text-ink-gray-8">View tree</RouterLink>
					</div>
					<DataTable
						class="mt-2"
						row-key="cost_center"
						:columns="[
							{ key: 'cost_center', label: 'Cost Center' },
							{ key: 'spending', label: 'Spent', align: 'right', format: (v: number) => fmt(v) },
							{ key: 'budget', label: 'Budget', align: 'right', format: (v: number) => (v ? fmt(v) : '—') },
						]"
						:rows="data.top_cost_centers"
						empty-text="No spending recorded this year"
					/>
				</section>
				<section v-if="data.recent_entries" class="card">
					<div class="flex items-center justify-between px-4 pt-4 sm:px-6">
						<h2 class="text-base font-semibold">Recent entries</h2>
						<div class="flex gap-3 text-sm text-ink-gray-5">
							<RouterLink to="/expenses" class="hover:text-ink-gray-8">Expenses</RouterLink>
							<RouterLink to="/journals" class="hover:text-ink-gray-8">Journal entries</RouterLink>
						</div>
					</div>
					<DataTable
						class="mt-2"
						:columns="[
							{ key: 'posting_date', label: 'Date', format: (v: string) => date(v) },
							{ key: 'title', label: 'Description', class: 'max-w-56 truncate' },
							{ key: 'voucher_type', label: 'Type' },
							{ key: 'total_debit', label: 'Amount', align: 'right', format: (v: number) => fmt(v) },
						]"
						:rows="data.recent_entries"
						clickable
						empty-text="No posted entries yet"
						@row-click="(r: any) => $router.push(entryPath(r.name, r.voucher_type))"
					>
						<template #voucher_type="{ value }"><StatusBadge :status="value" /></template>
					</DataTable>
				</section>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue"
import { Button, LoadingText, toast } from "frappe-ui"
import BarChart from "@/components/BarChart.vue"
import DataTable from "@/components/DataTable.vue"
import PageHeader from "@/components/PageHeader.vue"
import StatCard from "@/components/StatCard.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import UsageBar from "@/components/UsageBar.vue"
import { api } from "@/api"
import { date, entryPath, money, percent, today, utilizationTone } from "@/format"
import { can, currency, session } from "@/store"

const data = ref<any>(null)
const posting = ref(false)
const fmt = (v: number) => money(v, currency.value)

async function load() {
	data.value = await api("spend.api.get_dashboard", { company: session.company })
}

async function postDue() {
	posting.value = true
	try {
		const posted = await api<string[]>("spend.spend.depreciation.post_due_depreciation", { company: session.company, date: today() })
		toast.success(`${posted.length} depreciation entries posted`)
		await load()
	} finally {
		posting.value = false
	}
}

onMounted(load)
</script>
