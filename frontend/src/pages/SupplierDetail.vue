<template>
	<div v-if="!detail" class="p-6"><LoadingText /></div>
	<div v-else>
		<PageHeader :title="supplier.supplier_name" :subtitle="supplier.tax_id ? `Tax ID ${supplier.tax_id}` : undefined" :back="{ to: '/suppliers', label: 'Suppliers' }">
			<template #badge><Badge v-if="supplier.disabled" theme="gray" label="Disabled" /></template>
			<template #actions>
				<Button label="Open in Desk" icon-left="lucide-external-link" @click="openDesk" />
				<Button v-if="can('Supplier Payment', 'create') && detail.outstanding > 0" icon-left="lucide-banknote" label="Pay" @click="$router.push({ path: '/payments/new', query: { supplier: name } })" />
				<Button v-if="can('Purchase Invoice', 'create') && !supplier.disabled" variant="solid" icon-left="lucide-plus" label="New Bill" @click="$router.push({ path: '/bills/new', query: { supplier: name } })" />
			</template>
		</PageHeader>

		<div class="space-y-6 p-4 sm:p-6">
			<div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
				<StatCard label="Invoiced" :value="fmt(detail.invoiced)" :hint="`${submittedBills} bills`" />
				<StatCard label="Outstanding" :value="fmt(detail.outstanding)" :tone="detail.outstanding > 0 ? 'amber' : 'green'" />
				<StatCard label="Overdue" :value="fmt(detail.overdue)" :tone="detail.overdue > 0 ? 'red' : undefined" />
			</div>

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
					<h2 class="px-4 pt-4 text-base font-semibold sm:px-6">Bills</h2>
					<DataTable class="mt-2" :columns="billColumns" :rows="detail.invoices" clickable empty-text="No bills yet" @row-click="(r) => $router.push(`/bills/${r.name}`)">
						<template #status="{ value }"><StatusBadge :status="value" /></template>
					</DataTable>
				</section>
			</div>

			<section class="rounded-xl border border-outline-gray-1">
				<h2 class="px-4 pt-4 text-base font-semibold sm:px-6">Payments</h2>
				<DataTable class="mt-2" :columns="paymentColumns" :rows="detail.payments" empty-text="No payments yet">
					<template #name="{ value }"><a :href="`/app/supplier-payment/${value}`" class="hover:underline">{{ value }}</a></template>
					<template #docstatus="{ value }"><StatusBadge :status="docstatusLabel(value)" /></template>
				</DataTable>
			</section>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { Badge, Button, LoadingText } from "frappe-ui"
import DataTable, { type Column } from "@/components/DataTable.vue"
import PageHeader from "@/components/PageHeader.vue"
import StatCard from "@/components/StatCard.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import { api } from "@/api"
import { date, docstatusLabel, money } from "@/format"
import { can, currency, session } from "@/store"

const props = defineProps<{ name: string }>()

const detail = ref<any>(null)
const supplier = computed(() => detail.value.doc)
const fmt = (v: number) => money(v, currency.value)
const submittedBills = computed(() => detail.value.invoices.filter((i: any) => !["Draft", "Cancelled"].includes(i.status)).length)

const details = computed(() => [
	["Email", supplier.value.email],
	["Phone", supplier.value.phone],
	["Address", supplier.value.address],
])

const billColumns: Column[] = [
	{ key: "posting_date", label: "Date", format: date },
	{ key: "name", label: "Bill" },
	{ key: "bill_no", label: "Supplier Ref" },
	{ key: "due_date", label: "Due", format: date },
	{ key: "status", label: "Status" },
	{ key: "grand_total", label: "Total", align: "right", format: (v) => fmt(v) },
	{ key: "outstanding_amount", label: "Outstanding", align: "right", format: (v, r) => (["Draft", "Cancelled"].includes(r.status) ? "—" : fmt(v)) },
]

const paymentColumns: Column[] = [
	{ key: "posting_date", label: "Date", format: date },
	{ key: "name", label: "Payment" },
	{ key: "mode_of_payment", label: "Mode" },
	{ key: "reference_no", label: "Reference" },
	{ key: "docstatus", label: "Status" },
	{ key: "paid_amount", label: "Amount", align: "right", format: (v) => fmt(v) },
]

async function load() {
	detail.value = await api("spend.api.get_supplier_detail", { supplier: props.name, company: session.company })
}

function openDesk() {
	window.open(`/app/supplier/${encodeURIComponent(props.name)}`, "_blank")
}

onMounted(load)
watch(() => session.company, load)
</script>
