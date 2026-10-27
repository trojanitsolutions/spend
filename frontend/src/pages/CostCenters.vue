<template>
	<div>
		<PageHeader title="Cost Centers" subtitle="Spending rolls up from each cost center to its parents">
			<template #actions>
				<div class="w-44">
					<FormControl v-model="fiscalYear" type="select" :options="session.fiscalYears.map((f) => f.name)" aria-label="Fiscal year" />
				</div>
				<Button icon-left="lucide-external-link" label="Manage in Desk" @click="openDesk" />
			</template>
		</PageHeader>
		<TreeTable
			class="mt-2"
			:rows="rows"
			:loading="loading"
			name-field="cost_center"
			parent-field="parent_cost_center"
			:collapsed="collapsed"
			:columns="[
				{ key: 'spending', label: 'Spent', align: 'right', format: (v: number) => fmt(v) },
				{ key: 'budget', label: 'Budget', align: 'right', format: (v: number) => (v ? fmt(v) : '—') },
				{ key: 'variance', label: 'Remaining', align: 'right', format: (v: number | null) => (v == null ? '—' : fmt(v)) },
				{ key: 'share', label: 'Share', align: 'right', format: (v: number) => percent(v) },
			]"
			@toggle="toggle"
		/>
	</div>
</template>

<script setup lang="ts">
import { ref, watch } from "vue"
import { Button, FormControl } from "frappe-ui"
import PageHeader from "@/components/PageHeader.vue"
import TreeTable from "@/components/TreeTable.vue"
import { runReport } from "@/api"
import { money, percent } from "@/format"
import { currency, session } from "@/store"

const rows = ref<any[]>([])
const loading = ref(false)
const collapsed = ref(new Set<string>())
const fiscalYear = ref(session.currentFiscalYear || session.fiscalYears[0]?.name || "")
const fmt = (v: number) => money(v, currency.value)

function toggle(name: string) {
	const next = new Set(collapsed.value)
	next.has(name) ? next.delete(name) : next.add(name)
	collapsed.value = next
}

function openDesk() {
	window.open(`/app/cost-center/view/tree?company=${encodeURIComponent(session.company)}`, "_blank")
}

watch(
	fiscalYear,
	async () => {
		const fy = session.fiscalYears.find((f) => f.name === fiscalYear.value)
		if (!fy) return
		loading.value = true
		try {
			const result = await runReport("Cost Center-wise Spending", { company: session.company, from_date: fy.start_date, to_date: fy.end_date })
			rows.value = result.result
		} finally {
			loading.value = false
		}
	},
	{ immediate: true },
)
</script>
