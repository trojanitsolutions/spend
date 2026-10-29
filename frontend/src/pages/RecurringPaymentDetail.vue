<template>
	<div v-if="!detail" class="p-6"><LoadingText /></div>
	<div v-else>
		<PageHeader :title="rp.title" :subtitle="subtitle" :back="{ to: '/recurring', label: 'Recurring Payments' }">
			<template #badge><StatusBadge :status="rp.status" /></template>
			<template #actions>
				<Button v-if="deskAccess" label="Open in Desk" icon-left="lucide-external-link" @click="openDesk" />
				<template v-if="detail.can_submit">
					<Button v-if="rp.docstatus === 0 && !needsApproval('Recurring Payment')" variant="solid" label="Activate" :loading="busy" @click="activate" />
					<template v-if="rp.status === 'Active'">
						<Button label="Stop" :loading="busy" @click="run('stop', 'Stopped. Later payments are skipped until you resume.')" />
						<Button v-if="dueCount" variant="solid" :label="`Post ${dueCount} due now`" :loading="busy" @click="run('post_due_payments', 'Due payments posted')" />
					</template>
					<Button v-if="rp.status === 'Stopped'" variant="solid" label="Resume" :loading="busy" @click="run('resume', 'Resumed')" />
				</template>
				<template v-if="rp.docstatus === 1 && detail.can_cancel">
					<Button theme="red" label="Cancel" :loading="busy" @click="cancel(false)" />
					<Button variant="solid" label="Cancel & Amend" icon-left="lucide-pencil" :loading="busy" @click="cancel(true)" />
				</template>
				<Button v-if="rp.docstatus === 2 && !amendedAs && can('Recurring Payment', 'create')" variant="solid" label="Amend" icon-left="lucide-pencil" @click="amend" />
			</template>
		</PageHeader>

		<DocLayout doctype="Recurring Payment" :name="name" :version="rp.modified">
			<div class="space-y-6">
				<VersionsCard :name="name" base="recurring" :versions="versions" :currency="rp.currency" />
				<ApprovalBar doctype="Recurring Payment" :name="name" @changed="load" />
				<div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
					<StatCard label="Total" :value="fmt(rp.total_amount)" :hint="`${rp.schedule.length} payments · ${rp.frequency}`" />
					<StatCard label="Paid" :value="fmt(rp.paid_amount)" :hint="`${paidRows.length} posted`" />
					<StatCard label="Remaining" :value="fmt(rp.total_amount - rp.paid_amount)" />
					<StatCard label="Next payment" :value="next ? date(next.payment_date) : '—'" :hint="next ? fmt(next.amount) : 'Nothing left'" :tone="next && rowStatus(next) === 'Due' ? 'amber' : undefined" />
				</div>
				<p v-if="room" class="text-sm text-ink-gray-6">
					<template v-if="room.share">{{ detail.project_name || rp.project }}'s share of {{ room.account }} on </template>
					<template v-else>{{ room.account }} on </template>
					<RouterLink :to="`/budgets/${rp.budget}`" class="hover:underline">{{ rp.budget }}</RouterLink>:
					<template v-if="room.limit === null">no limit</template>
					<template v-else>
						{{ fmt(room.limit) }} · held {{ fmt(room.held) }}{{ rp.docstatus === 1 ? " with this payment" : "" }} ·
						<b :class="room.free < 0 || (rp.docstatus === 0 && room.free < rp.total_amount) ? 'text-ink-red-4' : 'text-ink-gray-9'">{{ fmt(room.free) }} free</b>
						<template v-if="rp.docstatus === 0"> · this payment needs {{ fmt(rp.total_amount) }}</template>
					</template>
				</p>

				<section class="card">
					<h2 class="px-4 pt-4 text-base font-semibold sm:px-6">Payment schedule</h2>
					<DataTable class="mt-2" :columns="scheduleColumns" :rows="rp.schedule">
						<template #status="{ row }"><StatusBadge :status="rowStatus(row)" /></template>
						<template #journal_entry="{ value }">
							<RouterLink v-if="value" :to="`/entries/${value}`" class="hover:underline" @click.stop>{{ value }}</RouterLink>
							<span v-else class="text-ink-gray-5">—</span>
						</template>
					</DataTable>
				</section>

				<section class="card p-4">
					<h2 class="mb-3 text-base font-semibold">Details</h2>
					<dl class="grid grid-cols-1 gap-x-8 gap-y-3 text-sm sm:grid-cols-2">
						<div v-for="[label, value] in details" :key="label" class="flex justify-between gap-4">
							<dt class="text-ink-gray-5">{{ label }}</dt>
							<dd class="whitespace-pre-line break-words text-right text-ink-gray-8">
								<RouterLink v-if="label === 'Budget' && value" :to="`/budgets/${value}`" class="hover:underline">{{ value }}</RouterLink>
								<template v-else>{{ value || "—" }}</template>
							</dd>
						</div>
					</dl>
				</section>
			</div>
		</DocLayout>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { Button, dialog, LoadingText, toast } from "frappe-ui"
import ApprovalBar from "@/components/ApprovalBar.vue"
import DataTable, { type Column } from "@/components/DataTable.vue"
import DocLayout from "@/components/DocLayout.vue"
import PageHeader from "@/components/PageHeader.vue"
import StatCard from "@/components/StatCard.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import VersionsCard from "@/components/VersionsCard.vue"
import { api, cancelDoc, categoryLabel, getRecurringRoom, getVersions, submitDoc, type RecurringRoom, type Version } from "@/api"
import { date, money, today } from "@/format"
import { can, currency, deskAccess, needsApproval } from "@/store"

const METHOD = "spend.purchasing.doctype.recurring_payment.recurring_payment"

const props = defineProps<{ name: string }>()

const router = useRouter()
const detail = ref<any>(null)
const versions = ref<Version[]>([])
const busy = ref(false)
// what is left of the Budget (or the project's share) for this payment's account
const room = ref<(RecurringRoom["accounts"][number] & { share: boolean }) | null>(null)
const amendedAs = computed(() => versions.value[versions.value.findIndex((v) => v.name === props.name) + 1])
const rp = computed(() => detail.value.doc)
const fmt = (v: number) => money(v, rp.value?.currency || currency.value)

const paidRows = computed(() => rp.value.schedule.filter((r: any) => r.journal_entry))
const next = computed(() => rp.value.schedule.find((r: any) => !r.journal_entry))
const dueCount = computed(() => rp.value.schedule.filter((r: any) => rowStatus(r) === "Due").length)
const subtitle = computed(() => [rp.value.name, rp.value.payee && `Payee: ${rp.value.payee}`, `${date(rp.value.from_date)} – ${date(rp.value.to_date)}`].filter(Boolean).join(" · "))

const scheduleColumns: Column[] = [
	{ key: "payment_date", label: "Date", format: date },
	{ key: "amount", label: "Amount", align: "right", format: (v) => fmt(v) },
	{ key: "status", label: "Status" },
	{ key: "journal_entry", label: "Entry" },
]

const details = computed(() => {
	const numbered = (account: string) => [detail.value.account_numbers[account], account].filter(Boolean).join(" · ")
	return [
		["Paid from (debit)", numbered(rp.value.expense_account)],
		["Paid to (credit)", numbered(rp.value.paid_from)],
		["Project", rp.value.project],
		["Category", categoryLabel(rp.value.expense_category, rp.value.expense_sub_category)],
		["Budget", rp.value.budget],
		["Cost center", rp.value.cost_center],
		["Frequency", rp.value.frequency],
		["Remarks", rp.value.remarks],
	]
})

function rowStatus(row: any) {
	if (row.journal_entry) return "Paid"
	if (rp.value.docstatus === 2) return "Cancelled"
	if (rp.value.status === "Stopped") return "Skipped"
	if (rp.value.docstatus === 1 && row.payment_date <= today()) return "Due"
	return "Upcoming"
}

async function load() {
	const [result, chain] = await Promise.all([api("spend.api.get_recurring_payment_detail", { name: props.name }), getVersions("Recurring Payment", props.name)])
	versions.value = chain
	detail.value = result
	loadRoom()
}

async function loadRoom() {
	const doc = rp.value
	room.value = null
	if (!doc.budget || doc.docstatus === 2) return
	// the user may not read the Budget; the line is then left out
	const result = await getRecurringRoom(doc.budget, doc.project || undefined, true).catch(() => null)
	const row = result?.accounts.find((r) => r.account === doc.expense_account)
	room.value = row ? { ...row, share: result!.share } : null
}

async function act(action: () => Promise<any>, message: string) {
	busy.value = true
	try {
		await action()
		toast.success(message)
		await load()
	} finally {
		busy.value = false
	}
}

function run(method: string, message: string) {
	return act(() => api(`${METHOD}.${method}`, { name: props.name }), message)
}

function activate() {
	dialog.confirm({
		title: "Activate recurring payment?",
		message: "Each payment is posted to the ledger on its date. Payments dated today or earlier are posted now.",
		confirmLabel: "Activate",
		onConfirm: () => act(() => submitDoc("Recurring Payment", props.name), "Activated"),
	})
}

function amend() {
	router.push({ path: "/recurring/new", query: { amend: props.name } })
}

function cancel(thenAmend: boolean) {
	const paid = paidRows.value.length ? " Payments already posted stay on the books." : ""
	dialog.confirm({
		title: thenAmend ? "Cancel and amend this recurring payment?" : "Cancel recurring payment?",
		message: thenAmend
			? `No more payments are posted from ${props.name}.${paid} You then edit a copy for the unpaid part and send it for approval.`
			: `No more payments are posted.${paid} You can amend it afterwards.`,
		confirmLabel: thenAmend ? "Cancel & Amend" : "Cancel Payment",
		theme: "red",
		onConfirm: () =>
			act(async () => {
				await cancelDoc("Recurring Payment", props.name)
				if (thenAmend) amend()
			}, "Cancelled"),
	})
}

function openDesk() {
	window.open(`/app/recurring-payment/${props.name}`, "_blank")
}

onMounted(load)
watch(() => props.name, load)
</script>
