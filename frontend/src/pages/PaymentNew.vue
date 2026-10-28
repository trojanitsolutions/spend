<template>
	<div>
		<PageHeader title="Pay Supplier" subtitle="Settles open bills from a cash or bank account" :back="{ to: '/payments', label: 'Payments' }" />

		<form class="mx-auto max-w-4xl space-y-6 p-4 sm:p-6" @submit.prevent="pay">
			<fieldset class="grid grid-cols-1 gap-4 rounded-xl border border-outline-gray-1 p-4 sm:grid-cols-2">
				<legend class="px-1 text-base font-semibold">Payment</legend>
				<LinkField
					v-model="doc.supplier"
					v-tour="{ key: 'payment.supplier', value: doc.supplier }"
					doctype="Supplier"
					label="Supplier"
					required
					:description="doc.supplier && supplierBalance !== null ? `Pending balance ${fmt(supplierBalance)}` : undefined"
				/>
				<FormControl v-model="doc.posting_date" v-tour="{ key: 'payment.posting_date', value: doc.posting_date }" type="date" label="Payment date" required />
				<LinkField
					v-model="doc.paid_from"
					v-tour="{ key: 'payment.paid_from', value: doc.paid_from }"
					doctype="Account"
					label="Paid from"
					required
					description="Cash or bank account"
					:filters="{ company: session.company, is_group: 0, disabled: 0, account_type: ['in', ['Cash', 'Bank']] }"
				/>
				<FormControl v-model="doc.mode_of_payment" v-tour="'payment.mode'" type="select" label="Mode" :options="MODES" />
				<FormControl v-model="doc.reference_no" v-tour="'payment.reference_no'" label="Reference no." placeholder="Cheque or transaction number" />
				<FormControl v-model="doc.reference_date" type="date" label="Reference date" />
				<LinkField
					v-model="doc.project"
					v-tour="{ key: 'payment.project', value: doc.project }"
					doctype="Project"
					label="Project"
					:description="autoProject ? 'The project of every selected bill' : doc.project ? 'Only bills of this project are listed' : 'Optional'"
					:filters="{ company: session.company }"
				/>
			</fieldset>

			<fieldset class="rounded-xl border border-outline-gray-1">
				<legend class="ml-4 px-1 text-base font-semibold">Open bills</legend>
				<p v-if="!doc.supplier" class="px-4 py-8 text-center text-sm text-ink-gray-5">Select a supplier to see what you owe them.</p>
				<div v-else-if="loadingBills" class="px-4 py-8 text-center"><LoadingText /></div>
				<p v-else-if="!bills.length" class="px-4 py-8 text-center text-sm text-ink-gray-5">Nothing is owed to {{ doc.supplier }}.</p>
				<div v-else class="overflow-x-auto">
					<table class="w-full min-w-max text-left text-base">
						<thead>
							<tr class="border-b border-outline-gray-1 text-sm text-ink-gray-5">
								<th scope="col" class="w-10 py-2 pl-4"><span class="sr-only">Pay</span></th>
								<th scope="col" class="px-3 py-2 font-medium">Bill</th>
								<th scope="col" class="px-3 py-2 font-medium">Due</th>
								<th scope="col" class="px-3 py-2 text-right font-medium">Outstanding</th>
								<th scope="col" class="w-40 py-2 pl-3 pr-4 text-right font-medium">Pay now</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="bill in bills" :key="bill.name" class="border-b border-outline-gray-1 last:border-0">
								<td class="py-2 pl-4">
									<input
										v-model="bill.selected"
										type="checkbox"
										class="rounded border-outline-gray-3"
										:aria-label="`Pay ${bill.name}`"
										@change="bill.allocated = bill.selected ? bill.outstanding_amount : 0"
									/>
								</td>
								<td class="px-3 py-2">
									<div class="font-medium text-ink-gray-9">{{ bill.name }}</div>
									<div v-if="bill.bill_no || bill.project" class="text-sm text-ink-gray-5">{{ [bill.bill_no, bill.project].filter(Boolean).join(" · ") }}</div>
								</td>
								<td class="whitespace-nowrap px-3 py-2" :class="bill.due_date < today() ? 'text-ink-red-4' : ''">{{ date(bill.due_date) }}</td>
								<td class="px-3 py-2 text-right tabular-nums">{{ fmt(bill.outstanding_amount) }}</td>
								<td class="py-2 pl-3 pr-4">
									<FormControl
										v-model="bill.allocated"
										type="number"
										min="0"
										:max="bill.outstanding_amount"
										step="0.01"
										:disabled="!bill.selected"
										:aria-label="`Amount for ${bill.name}`"
									/>
								</td>
							</tr>
						</tbody>
					</table>
				</div>
			</fieldset>

			<div class="flex flex-wrap items-center justify-end gap-3">
				<span v-if="overpaid" class="text-sm text-ink-red-4">An amount is more than the bill's outstanding.</span>
				<span class="text-base font-semibold tabular-nums">Paying {{ fmt(total) }}</span>
				<Button v-tour="'payment.submit'" type="submit" variant="solid" :label="needsApproval('Supplier Payment') ? 'Send for Approval' : 'Submit Payment'" :loading="saving" :disabled="!total || overpaid || !can('Supplier Payment', 'submit')" />
			</div>
		</form>
	</div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { Button, FormControl, LoadingText, toast } from "frappe-ui"
import LinkField from "@/components/LinkField.vue"
import PageHeader from "@/components/PageHeader.vue"
import { api, insertDoc } from "@/api"
import { date, money, today } from "@/format"
import { can, currency, needsApproval, session, submitOrSend } from "@/store"

const MODES = ["Bank Transfer", "Cash", "Cheque", "Card", "UPI"]

interface Bill {
	name: string
	bill_no?: string
	due_date: string
	outstanding_amount: number
	project?: string
	selected: boolean
	allocated: number | string
}

const route = useRoute()
const router = useRouter()
const saving = ref(false)
const loadingBills = ref(false)
const bills = ref<Bill[]>([])
const supplierBalance = ref<number | null>(null)
const fmt = (v: number) => money(v, currency.value)

const doc = reactive({
	supplier: (route.query.supplier as string) || "",
	posting_date: today(),
	paid_from: "",
	mode_of_payment: "Bank Transfer",
	reference_no: "",
	reference_date: "",
	project: (route.query.project as string) || "",
})

const allocations = computed(() => bills.value.filter((b) => b.selected && Number(b.allocated) > 0))
const total = computed(() => Math.round(allocations.value.reduce((t, b) => t + Number(b.allocated), 0) * 100) / 100)
const sharedProject = computed(() => {
	const projects = new Set(allocations.value.map((b) => b.project || ""))
	return projects.size === 1 ? [...projects][0] : ""
})
// the project filled in from the selected bills, as against one the user picked to filter them
const autoProject = ref("")
let settingProject = false
const overpaid = computed(() => allocations.value.some((b) => Number(b.allocated) - b.outstanding_amount > 0.005))

async function loadBalance() {
	supplierBalance.value = null
	if (!doc.supplier) return
	const supplier = doc.supplier
	const balance = await api<number>("spend.purchasing.doctype.supplier.supplier.get_outstanding", { supplier, company: session.company })
	if (supplier === doc.supplier) supplierBalance.value = balance || 0
}

async function loadBills() {
	bills.value = []
	if (!doc.supplier) return
	loadingBills.value = true
	try {
		const open = await api<any[]>("spend.purchasing.doctype.supplier_payment.supplier_payment.get_outstanding_invoices", {
			supplier: doc.supplier,
			company: session.company,
			project: doc.project || undefined,
		})
		const only = route.query.supplier === doc.supplier ? (route.query.invoice as string) : ""
		bills.value = open.map((b) => {
			const selected = !only || b.name === only
			return { ...b, selected, allocated: selected ? b.outstanding_amount : 0 }
		})
		syncProject()
	} finally {
		loadingBills.value = false
	}
}

async function pay() {
	if (!total.value || overpaid.value) return
	saving.value = true
	try {
		const payload: Record<string, any> = {
			doctype: "Supplier Payment",
			company: session.company,
			...doc,
			paid_amount: total.value,
			references: allocations.value.map((b) => ({ purchase_invoice: b.name, allocated_amount: Number(b.allocated) })),
		}
		if (!payload.reference_date) delete payload.reference_date
		if (!payload.project) delete payload.project
		const saved = await insertDoc<{ name: string }>(payload)
		const sent = await submitOrSend("Supplier Payment", saved.name)
		toast.success(sent ? `Payment ${saved.name} sent for approval` : `Payment ${saved.name} submitted`)
		router.push(`/payments/${saved.name}`)
	} finally {
		saving.value = false
	}
}

function setProject(value: string) {
	if (doc.project === value) return
	settingProject = true
	doc.project = value
	nextTick(() => (settingProject = false))
}

// tag the payment with the project the selected bills share, unless the user picked one
function syncProject() {
	if (doc.project && !autoProject.value) return
	autoProject.value = sharedProject.value
	setProject(sharedProject.value)
}

watch(sharedProject, syncProject)

watch(
	() => doc.supplier,
	() => {
		if (autoProject.value) {
			autoProject.value = ""
			setProject("")
		}
		loadBalance()
		loadBills()
	},
)

watch(
	() => doc.project,
	() => {
		if (settingProject) return
		autoProject.value = ""
		loadBills()
	},
)

onMounted(async () => {
	loadBalance()
	loadBills()
	const defaults = await api("spend.spend.doctype.company.company.get_company_defaults", { company: session.company })
	doc.paid_from ||= defaults.default_cash_account || ""
})
</script>
