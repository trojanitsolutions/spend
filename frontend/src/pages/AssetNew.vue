<template>
	<div>
		<PageHeader title="New Asset" :back="{ to: '/assets', label: 'Assets' }">
			<template #actions>
				<Button label="Save Draft" :loading="saving" @click="save(false)" />
				<Button v-if="can('Asset', 'submit')" variant="solid" label="Save & Submit" :loading="saving" @click="save(true)" />
			</template>
		</PageHeader>

		<form class="mx-auto grid max-w-5xl grid-cols-1 gap-6 p-4 sm:p-6 lg:grid-cols-5" @submit.prevent="save(false)">
			<div class="space-y-6 lg:col-span-3">
				<fieldset class="space-y-4 card p-4">
					<legend class="px-1 text-base font-semibold">Asset</legend>
					<FormControl v-model="doc.asset_name" label="Asset name" required placeholder="e.g. MacBook Pro 14" />
					<div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
						<FormControl v-model="doc.location" label="Location" />
						<LinkField v-model="doc.project" doctype="Project" label="Project" :filters="{ company: session.company, status: 'Open' }" description="Depreciation is charged to it" />
						<LinkField v-model="doc.cost_center" doctype="Cost Center" label="Cost center" :filters="{ company: session.company, is_group: 0 }" />
					</div>
					<div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
						<FormControl v-model="doc.gross_purchase_amount" type="number" label="Purchase amount" required min="0" step="0.01" />
						<FormControl v-model="doc.purchase_date" type="date" label="Purchase date" required />
						<FormControl v-model="doc.available_for_use_date" type="date" label="Capitalization date" required />
					</div>
				</fieldset>

				<fieldset class="space-y-4 card p-4">
					<legend class="px-1 text-base font-semibold">Depreciation</legend>
					<FormControl v-model="doc.calculate_depreciation" type="checkbox" label="Calculate depreciation" />
					<template v-if="doc.calculate_depreciation">
						<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
							<FormControl v-model="doc.depreciation_method" type="select" label="Method" :options="['Straight Line', 'Written Down Value']" />
							<FormControl v-model="doc.frequency_of_depreciation" type="select" label="Frequency" :options="['Monthly', 'Quarterly', 'Half-Yearly', 'Yearly']" />
							<FormControl v-model="doc.useful_life_years" type="number" label="Useful life (years)" min="0" step="0.25" required />
							<FormControl v-model="doc.salvage_value" type="number" label="Salvage value" min="0" step="0.01" />
							<FormControl v-model="doc.depreciation_start_date" type="date" label="First depreciation date" description="Defaults to the end of the first period" />
							<FormControl
								v-if="doc.depreciation_method === 'Written Down Value'"
								v-model="doc.rate_of_depreciation"
								type="number"
								label="Annual rate (%)"
								min="0"
								max="100"
								step="0.01"
								description="Leave empty to derive it from the salvage value"
							/>
						</div>
					</template>
				</fieldset>

				<fieldset class="space-y-4 card p-4">
					<legend class="px-1 text-base font-semibold">Accounts</legend>
					<p class="text-sm text-ink-gray-5">Prefilled from the company defaults.</p>
					<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
						<LinkField v-model="doc.fixed_asset_account" doctype="Account" label="Fixed asset account" required :filters="ledger('Asset', 'Fixed Asset')" />
						<LinkField v-model="doc.capitalization_credit_account" doctype="Account" label="Paid from / payable to" description="Credited on submit. Leave empty to skip the capitalization entry." :filters="{ company: session.company, is_group: 0, root_type: ['in', ['Asset', 'Liability', 'Equity']] }" />
						<LinkField v-if="doc.calculate_depreciation" v-model="doc.accumulated_depreciation_account" doctype="Account" label="Accumulated depreciation" :filters="ledger('Asset', 'Accumulated Depreciation')" />
						<LinkField v-if="doc.calculate_depreciation" v-model="doc.depreciation_expense_account" doctype="Account" label="Depreciation expense" :filters="ledger('Expense')" />
					</div>
				</fieldset>
			</div>

			<aside class="lg:col-span-2">
				<div class="sticky top-24 card p-4">
					<h2 class="text-base font-semibold">Schedule preview</h2>
					<p class="mb-3 text-sm text-ink-gray-5">Estimated in the browser. The saved schedule is computed on the server.</p>
					<p v-if="preview.error" class="text-sm text-ink-red-4">{{ preview.error }}</p>
					<template v-else-if="preview.rows.length">
						<div class="mb-3 grid grid-cols-2 gap-2 text-sm">
							<div class="rounded-lg bg-surface-gray-1 p-2">
								<div class="text-ink-gray-5">Periods</div>
								<div class="font-semibold">{{ preview.rows.length }}</div>
							</div>
							<div class="rounded-lg bg-surface-gray-1 p-2">
								<div class="text-ink-gray-5">First charge</div>
								<div class="font-semibold">{{ fmt(preview.rows[0].amount) }}</div>
							</div>
						</div>
						<div class="max-h-80 overflow-y-auto text-sm">
							<div v-for="row in preview.rows" :key="row.date" class="flex justify-between border-b border-outline-gray-1 py-1.5 tabular-nums last:border-0">
								<span class="text-ink-gray-6">{{ date(row.date) }}</span>
								<span>{{ fmt(row.amount) }}</span>
								<span class="text-ink-gray-5">{{ fmt(row.closing) }}</span>
							</div>
						</div>
					</template>
					<p v-else class="text-sm text-ink-gray-5">Enter amount, dates and useful life to preview.</p>
				</div>
			</aside>
		</form>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue"
import { useRoute, useRouter } from "vue-router"
import { Button, FormControl, toast } from "frappe-ui"
import LinkField from "@/components/LinkField.vue"
import PageHeader from "@/components/PageHeader.vue"
import { api, getDoc, insertDoc, submitDoc } from "@/api"
import { previewSchedule } from "@/depreciation"
import { date, money, today } from "@/format"
import { can, currency, session } from "@/store"

const route = useRoute()
const router = useRouter()
const saving = ref(false)
const fmt = (v: number) => money(v, currency.value)

const doc = reactive<Record<string, any>>({
	asset_name: "",
	location: "",
	project: (route.query.project as string) || "",
	cost_center: "",
	gross_purchase_amount: "",
	purchase_date: today(),
	available_for_use_date: today(),
	calculate_depreciation: true,
	depreciation_method: "Straight Line",
	frequency_of_depreciation: "Monthly",
	useful_life_years: 3,
	salvage_value: 0,
	depreciation_start_date: "",
	rate_of_depreciation: "",
	fixed_asset_account: "",
	capitalization_credit_account: "",
	accumulated_depreciation_account: "",
	depreciation_expense_account: "",
})

const ledger = (rootType: string, accountType?: string) => ({
	company: session.company,
	is_group: 0,
	root_type: rootType,
	...(accountType ? { account_type: accountType } : {}),
})

const preview = computed(() => {
	if (!doc.calculate_depreciation) return { rows: [], error: "" }
	return previewSchedule({
		cost: Number(doc.gross_purchase_amount),
		salvage: Number(doc.salvage_value || 0),
		method: doc.depreciation_method,
		frequency: doc.frequency_of_depreciation,
		usefulLifeYears: Number(doc.useful_life_years),
		availableForUseDate: doc.available_for_use_date,
		startDate: doc.depreciation_start_date,
		annualRate: Number(doc.rate_of_depreciation || 0),
	})
})

async function save(submit: boolean) {
	saving.value = true
	try {
		const payload = { doctype: "Asset", company: session.company, ...doc, calculate_depreciation: doc.calculate_depreciation ? 1 : 0 }
		for (const key of ["depreciation_start_date", "rate_of_depreciation", "capitalization_credit_account"]) {
			if (!payload[key]) delete payload[key]
		}
		const saved = await insertDoc<{ name: string }>(payload)
		if (submit) await submitDoc("Asset", saved.name)
		toast.success(submit ? "Asset submitted" : "Draft saved")
		router.replace(`/assets/${saved.name}`)
	} finally {
		saving.value = false
	}
}

onMounted(async () => {
	const [defaults, projectCostCenter] = await Promise.all([
		api("spend.spend.doctype.company.company.get_company_defaults", { company: session.company }),
		doc.project ? getDoc<{ cost_center?: string }>("Project", doc.project).then((p) => p.cost_center) : null,
	])
	Object.assign(doc, {
		cost_center: projectCostCenter || defaults.default_cost_center || "",
		fixed_asset_account: defaults.fixed_asset_account || "",
		accumulated_depreciation_account: defaults.accumulated_depreciation_account || "",
		depreciation_expense_account: defaults.depreciation_expense_account || "",
		capitalization_credit_account: defaults.default_payable_account || "",
	})
})
</script>
