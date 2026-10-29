<template>
	<div v-if="!entry" class="p-6"><LoadingText /></div>
	<div v-else>
		<PageHeader :title="entry.title" :subtitle="[entry.name, date(entry.posting_date), entry.payee && `Payee: ${entry.payee}`].filter(Boolean).join(' · ')" :back="entry.voucher_type && EXPENSE_TYPES.includes(entry.voucher_type) ? { to: '/expenses', label: 'Expenses' } : { to: '/journals', label: 'Journal Entries' }">
			<template #badge>
				<StatusBadge :status="entry.voucher_type" />
				<StatusBadge :status="docstatusLabel(entry.docstatus)" />
			</template>
			<template #actions>
				<Button v-if="deskAccess" label="Open in Desk" icon-left="lucide-external-link" @click="openDesk" />
				<Button
					v-if="entry.docstatus === 1"
					label="Ledger"
					icon-left="lucide-book-text"
					@click="$router.push({ path: '/reports/general-ledger', query: { voucher_no: entry.name, from_date: entry.posting_date, to_date: entry.posting_date } })"
				/>
				<Button v-if="entry.docstatus === 0 && can('Journal Entry', 'submit') && !needsApproval('Journal Entry')" variant="solid" label="Post" :loading="busy" @click="post" />
				<Button v-if="entry.docstatus === 1 && can('Journal Entry', 'submit') && !systemEntry" theme="red" label="Cancel Entry" :loading="busy" @click="cancel" />
			</template>
		</PageHeader>

		<DocLayout doctype="Journal Entry" :name="name" :version="entry.modified">
			<div class="space-y-6">
				<ApprovalBar v-if="!systemEntry" doctype="Journal Entry" :name="name" @changed="load" />

				<section class="card">
					<h2 class="px-4 pt-4 text-base font-semibold sm:px-6">Lines</h2>
					<DataTable class="mt-2" :columns="columns" :rows="entry.accounts">
						<template #asset="{ value }">
							<RouterLink v-if="value" :to="`/assets/${value}`" class="hover:underline" @click.stop>{{ value }}</RouterLink>
							<span v-else>—</span>
						</template>
					</DataTable>
					<div class="flex justify-end gap-6 border-t border-outline-gray-1 px-4 py-3 text-base font-semibold tabular-nums sm:px-6">
						<span>Debit {{ fmt(entry.total_debit) }}</span>
						<span>Credit {{ fmt(entry.total_credit) }}</span>
					</div>
				</section>

				<section v-if="entry.user_remark" class="card p-4">
					<h2 class="mb-2 text-base font-semibold">Description</h2>
					<p class="whitespace-pre-line text-sm text-ink-gray-8">{{ entry.user_remark }}</p>
				</section>
			</div>
		</DocLayout>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { Button, dialog, LoadingText, toast } from "frappe-ui"
import ApprovalBar from "@/components/ApprovalBar.vue"
import DataTable, { type Column } from "@/components/DataTable.vue"
import DocLayout from "@/components/DocLayout.vue"
import PageHeader from "@/components/PageHeader.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import { cancelDoc, categoryLabel, getDoc, submitDoc } from "@/api"
import { EXPENSE_TYPES, date, docstatusLabel, money } from "@/format"
import { can, currency, deskAccess, needsApproval } from "@/store"

const SYSTEM_TYPES = ["Depreciation Entry", "Asset Capitalization", "Recurring Payment"]

const props = defineProps<{ name: string }>()

const entry = ref<any>(null)
const busy = ref(false)
const fmt = (v: number) => money(v, entry.value?.currency || currency.value)
const systemEntry = computed(() => SYSTEM_TYPES.includes(entry.value.voucher_type))

// the asset column only shows when a line is a running cost of an asset
const columns = computed<Column[]>(() => [
	{ key: "account", label: "Account" },
	{ key: "cost_center", label: "Cost Center", format: (v) => v || "—" },
	{ key: "project", label: "Project", format: (v) => v || "—" },
	...(entry.value?.accounts.some((r: any) => r.asset) ? [{ key: "asset", label: "Asset" }] : []),
	{ key: "expense_category", label: "Category", format: (_, row) => categoryLabel(row.expense_category, row.expense_sub_category) || "—" },
	{ key: "debit", label: "Debit", align: "right", format: (v) => (v ? fmt(v) : "") },
	{ key: "credit", label: "Credit", align: "right", format: (v) => (v ? fmt(v) : "") },
])

async function load() {
	entry.value = await getDoc("Journal Entry", props.name)
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

function post() {
	dialog.confirm({
		title: "Post entry?",
		message: "Posting writes the lines to the ledger. Expense lines are checked against your budgets.",
		confirmLabel: "Post",
		onConfirm: () => run(() => submitDoc("Journal Entry", props.name), "Entry posted"),
	})
}

function cancel() {
	dialog.confirm({
		title: "Cancel entry?",
		message: "Its ledger lines are reversed and kept for the audit trail.",
		confirmLabel: "Cancel Entry",
		theme: "red",
		onConfirm: () => run(() => cancelDoc("Journal Entry", props.name), "Entry cancelled"),
	})
}

function openDesk() {
	window.open(`/app/journal-entry/${props.name}`, "_blank")
}

onMounted(load)
</script>
