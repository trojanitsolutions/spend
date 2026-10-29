<template>
	<div>
		<PageHeader title="New Project" subtitle="The project takes its budget as a share of a cost-center Budget" :back="{ to: '/projects', label: 'Projects' }">
			<template #actions>
				<Button variant="solid" :label="needsApproval('Project') ? 'Create & Send for Approval' : 'Create Project'" :loading="saving" @click="save" />
			</template>
		</PageHeader>

		<form class="mx-auto max-w-3xl space-y-6 p-4 sm:p-6" @submit.prevent="save">
			<fieldset class="grid grid-cols-1 gap-4 card p-4 sm:grid-cols-2">
				<legend class="px-1 text-base font-semibold">Project</legend>
				<FormControl v-model="doc.project_name" class="sm:col-span-2" label="Project name" required placeholder="e.g. Office fit-out 2026" />
				<FormControl v-model="doc.start_date" type="date" label="Start date" />
				<FormControl v-model="doc.end_date" type="date" label="End date" />
			</fieldset>

			<fieldset class="grid grid-cols-1 gap-4 card p-4 sm:grid-cols-2">
				<legend class="px-1 text-base font-semibold">Budget</legend>
				<LinkField
					v-model="doc.budget"
					doctype="Budget"
					label="Budget"
					required
					description="The cost-center Budget this project takes its share from"
					:filters="{ company: session.company, docstatus: 1 }"
				/>
				<LinkField
					v-model="doc.cost_center"
					doctype="Cost Center"
					label="Default cost center"
					:disabled="!allocation"
					description="Used on bill lines of this project without their own"
					:filters="costCenterFilters"
				/>
				<FormControl v-model="doc.action_if_exceeded" type="select" label="When exceeded" :options="['Warn', 'Stop', 'Ignore']" description="Checked when a bill or journal entry is submitted" />

				<div v-if="loadingBudget" class="sm:col-span-2"><LoadingText /></div>
				<div v-else-if="allocation" class="sm:col-span-2">
					<table class="w-full text-sm">
						<thead>
							<tr class="text-left text-ink-gray-5">
								<th class="pb-2 font-normal">Account</th>
								<th class="pb-2 text-right font-normal">Budget</th>
								<th class="hidden pb-2 text-right font-normal sm:table-cell">Held</th>
								<th class="pb-2 text-right font-normal">Free</th>
								<th class="w-36 pb-2 pl-3 font-normal">Project share</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="row in allocation.accounts" :key="row.account" class="border-t border-outline-gray-1">
								<td class="py-2 pr-3 text-ink-gray-8">{{ row.account }}</td>
								<td class="py-2 text-right tabular-nums text-ink-gray-6">{{ fmt(row.budget) }}</td>
								<td class="hidden py-2 text-right tabular-nums text-ink-gray-6 sm:table-cell">{{ fmt(row.held) }}</td>
								<td class="py-2 text-right tabular-nums" :class="row.free <= 0 ? 'text-ink-red-4' : 'text-ink-gray-8'">{{ fmt(row.free) }}</td>
								<td class="py-2 pl-3">
									<FormControl v-model="shares[row.account]" type="number" min="0" step="0.01" :aria-label="`Share of ${row.account}`" :class="{ over: Number(shares[row.account] || 0) > row.free }" />
								</td>
							</tr>
						</tbody>
						<tfoot>
							<tr class="border-t border-outline-gray-2 font-medium">
								<td class="py-2 text-ink-gray-8">Total</td>
								<td class="py-2 text-right tabular-nums text-ink-gray-6">{{ fmt(allocation.total) }}</td>
								<td class="hidden py-2 text-right tabular-nums text-ink-gray-6 sm:table-cell">{{ fmt(allocation.held) }}</td>
								<td class="py-2 text-right tabular-nums text-ink-gray-8">{{ fmt(allocation.free) }}</td>
								<td class="py-2 pl-3 text-right tabular-nums" :class="total > allocation.free ? 'text-ink-red-4' : 'text-ink-gray-9'">{{ fmt(total) }}</td>
							</tr>
						</tfoot>
					</table>
					<p class="mt-2 text-sm text-ink-gray-6">Leave a share empty to not use that account. Held is what other projects and recurring payments without a project take.</p>
				</div>
				<p v-else class="text-sm text-ink-gray-6 sm:col-span-2">Pick a Budget to see its accounts and what is still free.</p>
			</fieldset>

			<fieldset class="space-y-3 card p-4">
				<legend class="px-1 text-base font-semibold">Expense categories</legend>
				<p class="text-sm text-ink-gray-6">
					Bookings on the project can use only these categories. A row without a sub category covers the whole category. Leave the list empty to allow any category.
				</p>
				<div v-for="(row, i) in categories" :key="row.key" class="grid grid-cols-1 gap-2 rounded-lg bg-surface-gray-1 p-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_9rem_auto] sm:items-end sm:bg-transparent sm:p-0">
					<CategoryFields v-model:category="row.expense_category" v-model:sub-category="row.expense_sub_category" :labels="i === 0" />
					<FormControl v-model="row.budget_amount" type="number" min="0" step="0.01" :label="i === 0 ? 'Budget' : undefined" placeholder="No limit" :aria-label="`Budget of category ${i + 1}`" />
					<Button variant="ghost" icon="lucide-trash-2" :aria-label="`Remove category ${i + 1}`" @click="categories.splice(i, 1)" />
				</div>
				<div class="flex flex-wrap items-center justify-between gap-2 pt-1">
					<Button icon-left="lucide-plus" label="Add category" @click="addCategory" />
					<span v-if="categoryTotal" class="text-sm" :class="total && categoryTotal > total ? 'text-ink-red-4' : 'text-ink-gray-6'">
						Category budgets {{ fmt(categoryTotal) }}<template v-if="total"> of {{ fmt(total) }}</template>
					</span>
				</div>
			</fieldset>

			<FormControl v-model="doc.description" type="textarea" label="Description" />
		</form>
	</div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { Button, FormControl, LoadingText, toast } from "frappe-ui"
import CategoryFields from "@/components/CategoryFields.vue"
import LinkField from "@/components/LinkField.vue"
import PageHeader from "@/components/PageHeader.vue"
import { applyAction, APPROVAL, type BudgetAllocation, getBudgetAllocation, insertDoc } from "@/api"
import { money, today } from "@/format"
import { currency, needsApproval, session } from "@/store"

const router = useRouter()
const saving = ref(false)
const loadingBudget = ref(false)
const allocation = ref<BudgetAllocation | null>(null)
const shares = reactive<Record<string, number | string>>({})
const fmt = (v: number) => money(v, allocation.value?.currency || currency.value)

const doc = reactive({
	project_name: "",
	start_date: today(),
	end_date: "",
	budget: "",
	cost_center: "",
	action_if_exceeded: "Warn",
	description: "",
})

const categories = reactive<{ key: number; expense_category: string; expense_sub_category: string; budget_amount: number | string }[]>([])
let nextKey = 1
// a sub category's budget is part of its category's, unless the whole category has no row
const categoryTotal = computed(() =>
	categories
		.filter((r) => r.expense_category && (!r.expense_sub_category || !categories.some((c) => c.expense_category === r.expense_category && !c.expense_sub_category)))
		.reduce((t, r) => t + Number(r.budget_amount || 0), 0),
)

function addCategory() {
	categories.push({ key: nextKey++, expense_category: "", expense_sub_category: "", budget_amount: "" })
}

const total = computed(() => Object.values(shares).reduce((t: number, v) => t + Number(v || 0), 0))
const costCenterFilters = computed(() => {
	const filters: Record<string, any> = { company: session.company, is_group: 0, disabled: 0 }
	if (allocation.value) Object.assign(filters, { lft: [">=", allocation.value.lft], rgt: ["<=", allocation.value.rgt] })
	return filters
})

watch(
	() => doc.budget,
	async (budget) => {
		allocation.value = null
		for (const key of Object.keys(shares)) delete shares[key]
		if (!budget) return
		loadingBudget.value = true
		try {
			const result = await getBudgetAllocation(budget)
			if (budget !== doc.budget) return
			allocation.value = result
			doc.cost_center = result.cost_center_is_group ? "" : result.cost_center
			doc.action_if_exceeded = result.action_if_exceeded
		} finally {
			loadingBudget.value = false
		}
	},
)

async function save() {
	if (!doc.project_name.trim()) {
		toast.error("Enter a project name")
		return
	}
	if (!doc.budget) {
		toast.error("Pick a Budget")
		return
	}
	saving.value = true
	try {
		const payload: Record<string, any> = {
			doctype: "Project",
			company: session.company,
			...doc,
			budget_amount: total.value,
			budget_accounts: Object.entries(shares)
				.filter(([, amount]) => Number(amount) > 0)
				.map(([account, amount]) => ({ account, budget_amount: Number(amount) })),
			expense_categories: categories
				.filter((r) => r.expense_category)
				.map((r) => ({ expense_category: r.expense_category, expense_sub_category: r.expense_sub_category || undefined, budget_amount: Number(r.budget_amount || 0) })),
		}
		for (const key of ["start_date", "end_date", "cost_center"]) if (!payload[key]) delete payload[key]
		const saved = await insertDoc<{ name: string }>(payload)
		if (needsApproval("Project")) await applyAction("Project", saved.name, APPROVAL.send)
		toast.success(needsApproval("Project") ? `Project ${saved.name} sent for approval` : `Project ${saved.name} created`)
		router.replace(`/projects/${saved.name}`)
	} finally {
		saving.value = false
	}
}
</script>

<style scoped>
.over :deep(input) {
	border-color: var(--outline-red-3, #f87171);
}
</style>
