<template>
	<div v-if="!def"><EmptyState title="Report not found" icon="lucide-file-question" /></div>
	<div v-else>
		<PageHeader :title="def.name.replace(' Report', '')" :subtitle="def.description" :back="{ to: '/reports', label: 'Reports' }">
			<template #actions>
				<Button icon-left="lucide-download" label="CSV" :disabled="!result?.result.length" @click="downloadCsv" />
				<Button icon-left="lucide-external-link" label="Open in Desk" @click="openDesk" />
			</template>
		</PageHeader>

		<div class="flex flex-wrap items-end gap-3 border-b border-outline-gray-1 px-4 py-3 sm:px-6">
			<template v-for="f in def.filters" :key="f.fieldname">
				<div v-if="f.type === 'link'" class="w-full sm:w-56">
					<LinkField v-model="filters[f.fieldname]" :doctype="f.doctype!" :label="f.label" :filters="f.linkFilters?.(session.company)" />
				</div>
				<div v-else-if="f.type === 'fiscal_year'" class="w-full sm:w-44">
					<FormControl v-model="filters[f.fieldname]" type="select" :label="f.label" :options="session.fiscalYears.map((y) => y.name)" />
				</div>
				<div v-else-if="f.type === 'select'" class="w-full sm:w-44">
					<FormControl v-model="filters[f.fieldname]" type="select" :label="f.label" :options="f.options!.map((o) => ({ label: o || 'Any', value: o }))" />
				</div>
				<div v-else-if="f.type === 'text'" class="w-full sm:w-44">
					<FormControl v-model="filters[f.fieldname]" :label="f.label" :debounce="400" />
				</div>
				<div v-else-if="f.type === 'check'" class="pb-1.5">
					<FormControl v-model="filters[f.fieldname]" type="checkbox" :label="f.label" />
				</div>
				<div v-else class="w-full sm:w-40">
					<FormControl v-model="filters[f.fieldname]" type="date" :label="f.label" />
				</div>
			</template>
			<Button v-if="def.slug === 'depreciation-due' && can('Journal Entry', 'submit') && result?.result.length" variant="solid" class="sm:ml-auto" label="Post all due" :loading="posting" @click="postDue" />
		</div>

		<div v-if="result?.report_summary?.length" class="grid grid-cols-2 gap-3 px-4 pt-4 sm:px-6 lg:grid-cols-5">
			<StatCard v-for="s in result.report_summary" :key="s.label" :label="s.label" :value="formatSummary(s)" />
		</div>

		<section v-if="chart" class="mx-4 mt-4 rounded-xl border border-outline-gray-1 p-4 sm:mx-6">
			<BarChart :labels="chart.labels" :series="chart.series" :format="chart.format" />
		</section>

		<div class="mt-2">
			<TreeTable
				v-if="isTree"
				:rows="result?.result || []"
				:columns="valueColumns"
				:loading="loading"
				:name-field="treeFields!.name"
				:parent-field="treeFields!.parent"
				:collapsed="collapsed"
				@toggle="toggle"
			/>
			<DataTable
				v-else
				:columns="tableColumns"
				:rows="result?.result || []"
				:loading="loading"
				row-key="__idx"
				:clickable="hasVouchers"
				:row-class="(r) => (r.bold ? 'font-semibold bg-surface-gray-1' : undefined)"
				empty-text="No data for these filters"
				@row-click="openVoucher"
			/>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { Button, FormControl, toast } from "frappe-ui"
import BarChart from "@/components/BarChart.vue"
import DataTable, { type Column } from "@/components/DataTable.vue"
import EmptyState from "@/components/EmptyState.vue"
import LinkField from "@/components/LinkField.vue"
import PageHeader from "@/components/PageHeader.vue"
import StatCard from "@/components/StatCard.vue"
import TreeTable from "@/components/TreeTable.vue"
import { api, runReport, type ReportColumn, type ReportResult } from "@/api"
import { date, money, percent, today } from "@/format"
import { REPORTS } from "@/reports"
import { can, currency, session } from "@/store"

const TREES: Record<string, { name: string; parent: string }> = {
	"chart-of-accounts": { name: "account", parent: "parent_account" },
	"cost-center-wise-spending": { name: "cost_center", parent: "parent_cost_center" },
	"project-category-monthly": { name: "category", parent: "parent_category" },
}

const props = defineProps<{ slug: string }>()

const def = computed(() => REPORTS.find((r) => r.slug === props.slug))
const treeFields = computed(() => TREES[props.slug])
const isTree = computed(() => Boolean(treeFields.value))

const filters = reactive<Record<string, any>>({})
const result = ref<ReportResult | null>(null)
const loading = ref(false)
const posting = ref(false)
const collapsed = ref(new Set<string>())

// a link can set filters, e.g. ?project=PROJ-0001
const route = useRoute()
for (const f of def.value?.filters || []) {
	const fromLink = route.query[f.fieldname]
	filters[f.fieldname] = typeof fromLink === "string" ? fromLink : f.type === "fiscal_year" ? session.currentFiscalYear || session.fiscalYears[0]?.name || "" : f.default?.() ?? ""
}

function formatValue(col: ReportColumn, value: any): string {
	if (value == null || value === "") return ""
	switch (col.fieldtype) {
		case "Currency":
			return money(value, currency.value)
		case "Percent":
			return percent(value)
		case "Date":
			return date(value)
		case "Float":
			return Number(value).toLocaleString()
		default:
			return String(value)
	}
}

const visibleColumns = computed(() => (result.value?.columns || []).filter((c) => !c.hidden))
const toColumn = (c: ReportColumn): Column => ({
	key: c.fieldname,
	label: c.label,
	align: ["Currency", "Percent", "Float", "Int"].includes(c.fieldtype || "") ? "right" : "left",
	format: (v) => formatValue(c, v),
})
const tableColumns = computed(() => visibleColumns.value.map(toColumn))
const valueColumns = computed(() => visibleColumns.value.filter((c) => c.fieldname !== treeFields.value?.name).map(toColumn))

const chart = computed(() => {
	const c = result.value?.chart
	if (!c?.data?.labels?.length) return null
	const fieldtype = c.fieldtype
	return {
		labels: c.data.labels as string[],
		series: c.data.datasets.map((d: any) => ({ name: d.name, values: d.values.map(Number) })),
		format: (v: number) => (fieldtype === "Currency" ? money(v, currency.value) : fieldtype === "Percent" ? percent(v) : String(v)),
	}
})

function formatSummary(s: { value: number; datatype?: string }) {
	if (s.datatype === "Currency") return money(s.value, currency.value)
	if (s.datatype === "Percent") return percent(s.value)
	return String(s.value)
}

// ledger rows open the document that posted them
const VOUCHER_PATHS: Record<string, string> = {
	"Journal Entry": "/entries",
	"Purchase Invoice": "/bills",
	"Supplier Payment": "/payments",
	Asset: "/assets",
}
const router = useRouter()
const hasVouchers = computed(() => visibleColumns.value.some((c) => c.fieldname === "voucher_no"))

function openVoucher(row: Record<string, any>) {
	const base = VOUCHER_PATHS[row.voucher_type]
	if (base && row.voucher_no) router.push(`${base}/${row.voucher_no}`)
}

function toggle(name: string) {
	const next = new Set(collapsed.value)
	next.has(name) ? next.delete(name) : next.add(name)
	collapsed.value = next
}

async function run() {
	if (!def.value) return
	loading.value = true
	try {
		const data = await runReport(def.value.name, { company: session.company, ...filters })
		data.result = (data.result || []).filter((r: any) => r && !Array.isArray(r)).map((r: any, i: number) => ({ ...r, __idx: i }))
		result.value = data
	} finally {
		loading.value = false
	}
}

async function postDue() {
	posting.value = true
	try {
		const posted = await api<string[]>("spend.spend.depreciation.post_due_depreciation", {
			company: session.company,
			date: filters.as_on_date || today(),
		})
		toast.success(`${posted.length} depreciation entries posted`)
		await run()
	} finally {
		posting.value = false
	}
}

function downloadCsv() {
	const cols = visibleColumns.value
	const escape = (v: any) => `"${String(v ?? "").replace(/"/g, '""')}"`
	const lines = [cols.map((c) => escape(c.label)).join(",")]
	for (const row of result.value?.result || []) lines.push(cols.map((c) => escape(row[c.fieldname])).join(","))
	const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }))
	const a = Object.assign(document.createElement("a"), { href: url, download: `${props.slug}.csv` })
	a.click()
	URL.revokeObjectURL(url)
}

function openDesk() {
	window.open(`/app/query-report/${encodeURIComponent(def.value!.name)}?company=${encodeURIComponent(session.company)}`, "_blank")
}

watch(() => ({ ...filters }), run, { deep: true, immediate: true })
</script>
