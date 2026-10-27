<template>
	<div v-if="!detail" class="p-6"><LoadingText /></div>
	<div v-else>
		<PageHeader :title="bill.supplier" :subtitle="`${bill.name}${bill.bill_no ? ` · Supplier ref ${bill.bill_no}` : ''}`" :back="{ to: '/bills', label: 'Bills' }">
			<template #badge><StatusBadge :status="bill.status" /></template>
			<template #actions>
				<Button label="Open in Desk" icon-left="lucide-external-link" @click="openDesk" />
				<Button
					v-if="bill.docstatus === 1"
					label="Ledger"
					icon-left="lucide-book-text"
					@click="$router.push({ path: '/reports/general-ledger', query: { voucher_no: bill.name, from_date: bill.posting_date, to_date: bill.posting_date } })"
				/>
				<Button v-if="bill.docstatus === 0 && detail.can_submit && !needsApproval('Purchase Invoice')" variant="solid" label="Submit" :loading="busy" @click="submit" />
				<Button
					v-if="bill.docstatus === 1 && bill.outstanding_amount > 0 && can('Supplier Payment', 'create')"
					variant="solid"
					icon-left="lucide-banknote"
					label="Record Payment"
					@click="$router.push({ path: '/payments/new', query: { supplier: bill.supplier, invoice: bill.name } })"
				/>
				<Button v-if="bill.docstatus === 1 && detail.can_cancel" theme="red" label="Cancel Bill" :loading="busy" @click="cancelBill" />
			</template>
		</PageHeader>

		<div class="space-y-6 p-4 sm:p-6">
			<ApprovalBar doctype="Purchase Invoice" :name="name" @changed="load" />
			<div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
				<StatCard label="Total" :value="fmt(bill.grand_total)" :hint="`Posted ${date(bill.posting_date)}`" />
				<StatCard label="Paid" :value="fmt(paid)" :hint="`${activePayments.length} payments`" />
				<StatCard label="Outstanding" :value="fmt(bill.docstatus === 1 ? bill.outstanding_amount : bill.grand_total)" :tone="bill.status === 'Overdue' ? 'red' : undefined" />
				<StatCard label="Due" :value="date(bill.due_date)" :tone="bill.status === 'Overdue' ? 'red' : undefined" :hint="dueHint" />
			</div>

			<section class="rounded-xl border border-outline-gray-1">
				<h2 class="px-4 pt-4 text-base font-semibold sm:px-6">Items</h2>
				<DataTable class="mt-2" :columns="itemColumns" :rows="bill.items">
					<template #item_code="{ row }">
						<div class="font-medium text-ink-gray-9">
							{{ row.item_name || row.item_code || "—" }}<Badge v-if="row.is_fixed_asset" class="ml-2" theme="blue" label="Fixed asset" />
						</div>
						<div v-if="row.item_code && row.item_name !== row.item_code" class="text-sm text-ink-gray-5">{{ row.item_code }}</div>
					</template>
					<template #expense_account="{ value }">
						<span class="tabular-nums text-ink-gray-5">{{ detail.account_numbers[value] }}</span>
						<span class="ml-1">{{ value }}</span>
					</template>
				</DataTable>
				<div class="flex justify-end border-t border-outline-gray-1 px-4 py-3 text-base font-semibold tabular-nums sm:px-6">Total {{ fmt(bill.grand_total) }}</div>
			</section>

			<section v-if="detail.assets.length" class="rounded-xl border border-outline-gray-1">
				<h2 class="px-4 pt-4 text-base font-semibold sm:px-6">Assets from this bill</h2>
				<DataTable class="mt-2" :columns="assetColumns" :rows="detail.assets" clickable @row-click="(r) => $router.push(`/assets/${r.name}`)">
					<template #status="{ value }"><StatusBadge :status="value" /></template>
				</DataTable>
			</section>

			<div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
				<section class="rounded-xl border border-outline-gray-1 p-4">
					<h2 class="mb-3 text-base font-semibold">Details</h2>
					<dl class="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
						<template v-for="[label, value] in details" :key="label">
							<dt class="text-ink-gray-5">{{ label }}</dt>
							<dd class="whitespace-pre-line break-words text-right text-ink-gray-8">{{ value || "—" }}</dd>
						</template>
					</dl>
				</section>
				<section class="rounded-xl border border-outline-gray-1 lg:col-span-2">
					<h2 class="px-4 pt-4 text-base font-semibold sm:px-6">Payments</h2>
					<DataTable class="mt-2" :columns="paymentColumns" :rows="detail.payments" clickable empty-text="No payments yet" @row-click="(r) => $router.push(`/payments/${r.name}`)">
						<template #docstatus="{ value }"><StatusBadge :status="docstatusLabel(value)" /></template>
						<template #actions="{ row }">
							<Button v-if="row.docstatus === 1 && can('Supplier Payment', 'cancel')" size="sm" theme="red" label="Cancel" @click.stop="confirmCancelPayment(row.name, load)" />
						</template>
					</DataTable>
				</section>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { Badge, Button, dialog, LoadingText, toast } from "frappe-ui"
import ApprovalBar from "@/components/ApprovalBar.vue"
import DataTable, { type Column } from "@/components/DataTable.vue"
import PageHeader from "@/components/PageHeader.vue"
import StatCard from "@/components/StatCard.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import { api, cancelDoc, categoryLabel, submitDoc } from "@/api"
import { date, docstatusLabel, money, today } from "@/format"
import { confirmCancelPayment } from "@/payments"
import { can, currency, needsApproval } from "@/store"

const props = defineProps<{ name: string }>()

const detail = ref<any>(null)
const busy = ref(false)
const bill = computed(() => detail.value.doc)
const fmt = (v: number) => money(v, bill.value?.currency || currency.value)

const activePayments = computed(() => detail.value.payments.filter((p: any) => p.docstatus === 1))
const paid = computed(() => activePayments.value.reduce((t: number, p: any) => t + p.allocated_amount, 0))
const dueHint = computed(() => {
	if (bill.value.docstatus !== 1 || bill.value.outstanding_amount <= 0) return ""
	const days = Math.round((Date.parse(`${today()}T00:00:00`) - Date.parse(`${bill.value.due_date}T00:00:00`)) / 86400000)
	if (days > 0) return `${days} days overdue`
	return days === 0 ? "Due today" : `In ${-days} days`
})

const assetColumns: Column[] = [
	{ key: "name", label: "Asset" },
	{ key: "asset_name", label: "Name" },
	{ key: "status", label: "Status" },
	{ key: "gross_purchase_amount", label: "Amount", align: "right", format: (v) => fmt(v) },
]

const itemColumns: Column[] = [
	{ key: "item_code", label: "Item" },
	{ key: "description", label: "Description", class: "max-w-72 truncate" },
	{ key: "expense_account", label: "Account" },
	{ key: "cost_center", label: "Cost Center" },
	{ key: "project", label: "Project", format: (v) => v || "—" },
	{ key: "expense_category", label: "Category", format: (_, row) => categoryLabel(row.expense_category, row.expense_sub_category) || "—" },
	{
		key: "qty",
		label: "Qty",
		align: "right",
		format: (v, row) => (row.uom ? `${v} ${row.uom}` : v) + (row.conversion_factor && row.conversion_factor !== 1 ? ` (${row.stock_qty} ${row.stock_uom})` : ""),
	},
	{ key: "rate", label: "Rate", align: "right", format: (v) => fmt(v) },
	{ key: "amount", label: "Amount", align: "right", format: (v) => fmt(v) },
]

const paymentColumns: Column[] = [
	{ key: "posting_date", label: "Date", format: date },
	{ key: "name", label: "Payment" },
	{ key: "mode_of_payment", label: "Mode" },
	{ key: "reference_no", label: "Reference" },
	{ key: "docstatus", label: "Status" },
	{ key: "allocated_amount", label: "Amount", align: "right", format: (v) => fmt(v) },
	{ key: "actions", label: "", align: "right" },
]

const details = computed(() => [
	["Project", bill.value.project],
	["Supplier invoice date", date(bill.value.bill_date)],
	["Payable account", bill.value.credit_to],
	["Default cost center", bill.value.cost_center],
	["Fiscal year", bill.value.fiscal_year],
	["Remarks", bill.value.remarks],
])

async function load() {
	detail.value = await api("spend.api.get_purchase_invoice_detail", { invoice: props.name })
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
		title: "Submit bill?",
		message: "Submitting posts the expense and the amount owed to the ledger. It is checked against your budgets.",
		confirmLabel: "Submit",
		onConfirm: () => run(() => submitDoc("Purchase Invoice", props.name), "Bill submitted"),
	})
}

function cancelBill() {
	dialog.confirm({
		title: "Cancel bill?",
		message: "Its ledger entries are reversed and kept for the audit trail. Cancel any payments against it first.",
		confirmLabel: "Cancel Bill",
		theme: "red",
		onConfirm: () => run(() => cancelDoc("Purchase Invoice", props.name), "Bill cancelled"),
	})
}

function openDesk() {
	window.open(`/app/purchase-invoice/${props.name}`, "_blank")
}

onMounted(load)
</script>
