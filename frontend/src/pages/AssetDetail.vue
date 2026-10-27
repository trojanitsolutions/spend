<template>
	<div v-if="!detail" class="p-6"><LoadingText /></div>
	<div v-else>
		<PageHeader :title="asset.asset_name" :subtitle="`${asset.name} · ${asset.location || asset.company}`" :back="{ to: '/assets', label: 'Assets' }">
			<template #badge><StatusBadge :status="asset.status" /></template>
			<template #actions>
				<Button label="Open in Desk" icon-left="lucide-external-link" @click="openDesk" />
				<Button v-if="asset.docstatus === 0 && detail.can_submit" variant="solid" label="Submit" :loading="busy" @click="submit" />
				<Button v-if="canPost" variant="solid" icon-left="lucide-calendar-check" label="Post Due Depreciation" :loading="busy" @click="postDue" />
				<Button v-if="asset.docstatus === 1 && detail.can_submit" theme="red" label="Cancel Asset" :loading="busy" @click="cancelAsset" />
			</template>
		</PageHeader>

		<div class="space-y-6 p-4 sm:p-6">
			<div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
				<StatCard label="Gross value" :value="fmt(asset.gross_purchase_amount)" :hint="`Capitalized ${date(asset.available_for_use_date)}`" />
				<StatCard label="Accumulated depreciation" :value="fmt(asset.accumulated_depreciation)" :hint="`${posted} of ${detail.schedule.length} periods posted`" />
				<StatCard label="Book value" :value="fmt(asset.value_after_depreciation)" :hint="`Salvage ${fmt(asset.salvage_value)}`" />
				<StatCard label="Next depreciation" :value="next ? fmt(next.depreciation_amount) : '—'" :hint="next ? date(next.schedule_date) : 'Nothing scheduled'" />
			</div>

			<div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
				<section class="rounded-xl border border-outline-gray-1 p-4 lg:col-span-1">
					<h2 class="mb-3 text-base font-semibold">Details</h2>
					<dl class="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
						<template v-for="[label, value] in details" :key="label">
							<dt class="text-ink-gray-5">{{ label }}</dt>
							<dd class="break-words text-right text-ink-gray-8">{{ value || "—" }}</dd>
						</template>
					</dl>
				</section>

				<section class="rounded-xl border border-outline-gray-1 lg:col-span-2">
					<div class="flex flex-wrap items-center justify-between gap-2 px-4 pt-4 sm:px-6">
						<h2 class="text-base font-semibold">Depreciation schedule</h2>
						<div class="w-full sm:w-56"><UsageBar neutral :value="depreciatedPct" :caption="percent(depreciatedPct)" label="Depreciated" /></div>
					</div>
					<p v-if="!asset.calculate_depreciation" class="px-6 py-8 text-center text-sm text-ink-gray-5">This asset is not depreciated.</p>
					<DataTable v-else class="mt-2" :columns="scheduleColumns" :rows="scheduleRows" empty-text="Save the asset to generate its schedule">
						<template #journal_entry="{ row }">
							<a v-if="row.journal_entry" :href="`/app/journal-entry/${row.journal_entry}`" class="text-ink-blue-4 hover:underline">{{ row.journal_entry }}</a>
							<StatusBadge v-else :status="row.state" />
						</template>
					</DataTable>
				</section>
			</div>

			<section v-if="detail.entries.length" class="rounded-xl border border-outline-gray-1">
				<h2 class="px-4 pt-4 text-base font-semibold sm:px-6">Accounting entries</h2>
				<DataTable
					class="mt-2"
					:columns="[
						{ key: 'posting_date', label: 'Date', format: date },
						{ key: 'name', label: 'Entry' },
						{ key: 'voucher_type', label: 'Type' },
						{ key: 'docstatus', label: 'Status', format: docstatusLabel },
						{ key: 'total_debit', label: 'Amount', align: 'right', format: (v: number) => fmt(v) },
					]"
					:rows="detail.entries"
				>
					<template #voucher_type="{ value }"><StatusBadge :status="value" /></template>
					<template #name="{ value }"><a :href="`/app/journal-entry/${value}`" class="hover:underline">{{ value }}</a></template>
				</DataTable>
			</section>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { Button, dialog, LoadingText, toast } from "frappe-ui"
import DataTable, { type Column } from "@/components/DataTable.vue"
import PageHeader from "@/components/PageHeader.vue"
import StatCard from "@/components/StatCard.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import UsageBar from "@/components/UsageBar.vue"
import { api, cancelDoc, submitDoc } from "@/api"
import { date, docstatusLabel, money, percent, today } from "@/format"
import { currency } from "@/store"

const props = defineProps<{ name: string }>()

const detail = ref<any>(null)
const busy = ref(false)
const asset = computed(() => detail.value.doc)
const fmt = (v: number) => money(v, asset.value?.currency || currency.value)

const posted = computed(() => detail.value.schedule.filter((r: any) => r.journal_entry).length)
const next = computed(() => detail.value.schedule.find((r: any) => !r.journal_entry))
const canPost = computed(
	() => detail.value.can_submit && asset.value.docstatus === 1 && next.value && next.value.schedule_date <= today(),
)
const depreciatedPct = computed(() => {
	const depreciable = asset.value.gross_purchase_amount - asset.value.salvage_value
	return depreciable > 0 ? (asset.value.accumulated_depreciation / depreciable) * 100 : 0
})

const scheduleRows = computed(() =>
	detail.value.schedule.map((r: any) => ({ ...r, state: r.schedule_date <= today() ? "Due" : "Upcoming" })),
)
const scheduleColumns: Column[] = [
	{ key: "schedule_date", label: "Date", format: date },
	{ key: "opening_book_value", label: "Opening", align: "right", format: (v) => fmt(v) },
	{ key: "depreciation_amount", label: "Depreciation", align: "right", format: (v) => fmt(v) },
	{ key: "accumulated_depreciation_amount", label: "Accumulated", align: "right", format: (v) => fmt(v) },
	{ key: "closing_book_value", label: "Closing", align: "right", format: (v) => fmt(v) },
	{ key: "journal_entry", label: "Posting" },
]

const details = computed(() => {
	const a = asset.value
	return [
		["Cost center", a.cost_center],
		["Purchase date", date(a.purchase_date)],
		["Method", a.calculate_depreciation ? a.depreciation_method : "Not depreciated"],
		["Frequency", a.calculate_depreciation ? a.frequency_of_depreciation : ""],
		["Useful life", a.calculate_depreciation ? `${a.useful_life_years} years · ${a.total_number_of_depreciations} periods` : ""],
		["Starts", date(a.depreciation_start_date)],
		["Rate", a.depreciation_method === "Written Down Value" && a.rate_of_depreciation ? percent(a.rate_of_depreciation, 2) : ""],
		["Fixed asset account", a.fixed_asset_account],
		["Accumulated dep. account", a.accumulated_depreciation_account],
		["Expense account", a.depreciation_expense_account],
		["Capitalization entry", a.capitalization_entry],
	].filter(([, v]) => v !== "")
})

async function load() {
	detail.value = await api("spend.api.get_asset_detail", { asset: props.name })
}

async function run(action: () => Promise<any>, message: string) {
	busy.value = true
	try {
		await action()
		toast.success(message)
		await load()
	} finally {
		busy.value = false
	}
}

function submit() {
	dialog.confirm({
		title: "Submit asset?",
		message: "Submitting locks the asset, posts its capitalization entry and activates the depreciation schedule.",
		confirmLabel: "Submit",
		onConfirm: () => run(() => submitDoc("Asset", props.name), "Asset submitted"),
	})
}

function postDue() {
	run(async () => {
		const entries = await api<string[]>("spend.spend.depreciation.post_due_depreciation", { asset: props.name, date: today() })
		if (!entries.length) toast.info("No depreciation is due yet")
	}, "Depreciation posted")
}

function cancelAsset() {
	dialog.confirm({
		title: "Cancel asset?",
		message: "The schedule is cancelled and the capitalization entry reversed. Cancel any posted depreciation entries first.",
		confirmLabel: "Cancel Asset",
		theme: "red",
		onConfirm: () => run(() => cancelDoc("Asset", props.name), "Asset cancelled"),
	})
}

function openDesk() {
	window.open(`/app/asset/${props.name}`, "_blank")
}

onMounted(load)
</script>
