<template>
	<div v-if="!payment" class="p-6"><LoadingText /></div>
	<div v-else>
		<PageHeader :title="payment.supplier" :subtitle="`${payment.name} · ${date(payment.posting_date)}`" :back="{ to: '/payments', label: 'Payments' }">
			<template #badge><StatusBadge :status="docstatusLabel(payment.docstatus)" /></template>
			<template #actions>
				<Button label="Open in Desk" icon-left="lucide-external-link" @click="openDesk" />
				<Button
					v-if="payment.docstatus === 1"
					label="Ledger"
					icon-left="lucide-book-text"
					@click="$router.push({ path: '/reports/general-ledger', query: { voucher_no: payment.name, from_date: payment.posting_date, to_date: payment.posting_date } })"
				/>
				<Button v-if="payment.docstatus === 0 && can('Supplier Payment', 'submit') && !needsApproval('Supplier Payment')" variant="solid" label="Submit" :loading="busy" @click="submit" />
				<Button v-if="payment.docstatus === 1 && can('Supplier Payment', 'cancel')" theme="red" label="Cancel Payment" @click="confirmCancelPayment(name, load)" />
			</template>
		</PageHeader>

		<div class="space-y-6 p-4 sm:p-6">
			<ApprovalBar doctype="Supplier Payment" :name="name" @changed="load" />

			<div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
				<StatCard label="Paid" :value="fmt(payment.paid_amount)" :hint="payment.mode_of_payment" />
				<StatCard label="Allocated to bills" :value="fmt(payment.total_allocated)" :hint="`${payment.references.length} bills`" />
				<StatCard label="Paid from" :value="payment.paid_from" />
				<StatCard label="Reference" :value="payment.reference_no || '—'" :hint="payment.reference_date ? date(payment.reference_date) : ''" />
			</div>

			<section class="rounded-xl border border-outline-gray-1">
				<h2 class="px-4 pt-4 text-base font-semibold sm:px-6">Bills paid</h2>
				<DataTable class="mt-2" :columns="columns" :rows="payment.references" clickable @row-click="(r) => $router.push(`/bills/${r.purchase_invoice}`)" />
			</section>

			<section v-if="payment.project || payment.remarks" class="rounded-xl border border-outline-gray-1 p-4">
				<dl class="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
					<dt class="text-ink-gray-5">Project</dt>
					<dd class="text-right text-ink-gray-8">{{ payment.project || "—" }}</dd>
					<dt class="text-ink-gray-5">Remarks</dt>
					<dd class="whitespace-pre-line text-right text-ink-gray-8">{{ payment.remarks || "—" }}</dd>
				</dl>
			</section>
		</div>
	</div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue"
import { Button, dialog, LoadingText, toast } from "frappe-ui"
import ApprovalBar from "@/components/ApprovalBar.vue"
import DataTable, { type Column } from "@/components/DataTable.vue"
import PageHeader from "@/components/PageHeader.vue"
import StatCard from "@/components/StatCard.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import { getDoc, submitDoc } from "@/api"
import { confirmCancelPayment } from "@/payments"
import { date, docstatusLabel, money } from "@/format"
import { can, currency, needsApproval } from "@/store"

const props = defineProps<{ name: string }>()

const payment = ref<any>(null)
const busy = ref(false)
const fmt = (v: number) => money(v, payment.value?.currency || currency.value)

const columns: Column[] = [
	{ key: "purchase_invoice", label: "Bill" },
	{ key: "due_date", label: "Due", format: date },
	{ key: "grand_total", label: "Bill total", align: "right", format: (v) => fmt(v) },
	{ key: "allocated_amount", label: "Paid", align: "right", format: (v) => fmt(v) },
]

async function load() {
	payment.value = await getDoc("Supplier Payment", props.name)
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
		title: "Submit payment?",
		message: "The payment is posted to the ledger and reduces what is owed on the bills.",
		confirmLabel: "Submit",
		onConfirm: () => run(() => submitDoc("Supplier Payment", props.name), "Payment submitted"),
	})
}

function openDesk() {
	window.open(`/app/supplier-payment/${props.name}`, "_blank")
}

onMounted(load)
</script>
