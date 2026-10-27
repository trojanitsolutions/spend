<template>
	<div>
		<PageHeader title="Expense Accounts" subtitle="Numbered expense accounts and what has been spent on each">
			<template #actions>
				<div class="w-40"><FormControl v-model="asOn" type="date" aria-label="As on date" /></div>
				<Button icon-left="lucide-external-link" label="Full chart in Desk" @click="openDesk" />
				<Button v-if="can('Account', 'create')" variant="solid" icon-left="lucide-plus" label="New Account" @click="openNew" />
			</template>
		</PageHeader>
		<div class="flex flex-wrap items-center gap-2 px-4 py-3 sm:px-6">
			<div class="w-full sm:w-64">
				<TextInput v-model="query" type="search" placeholder="Search number or name" :debounce="150">
					<template #prefix><span class="lucide-search size-4 text-ink-gray-5" aria-hidden="true" /></template>
				</TextInput>
			</div>
			<Button class="ml-auto" variant="ghost" :label="allOpen ? 'Collapse all' : 'Expand all'" @click="toggleAll" />
		</div>
		<TreeTable
			:rows="visibleRows"
			:loading="loading"
			name-field="account"
			name-label="Account"
			parent-field="parent_account"
			:collapsed="query ? new Set() : collapsed"
			:label="(r) => (r.account_number ? `${r.account_number} · ${r.account_name}` : r.account_name)"
			:columns="[
				{ key: 'account_type', label: 'Type' },
				{ key: 'balance', label: 'Spent to date', align: 'right', format: (v: number) => fmt(v) },
			]"
			@toggle="toggle"
		/>

		<Dialog v-model:open="dialogOpen" title="New expense account" :actions="[{ label: 'Create', variant: 'solid', onClick: create }]">
			<form class="space-y-4" @submit.prevent="create">
				<div class="grid grid-cols-1 gap-4 sm:grid-cols-[8rem_1fr]">
					<FormControl v-model="draft.account_number" label="Number" required placeholder="e.g. 5210" />
					<FormControl v-model="draft.account_name" label="Account name" required placeholder="e.g. Courier Charges" />
				</div>
				<FormControl v-model="draft.parent_account" type="select" label="Under" :options="groups.map((g) => ({ label: groupLabel(g), value: g.account }))" />
				<FormControl v-model="draft.is_group" type="checkbox" label="This is a group (holds other accounts)" />
			</form>
		</Dialog>
	</div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue"
import { Button, Dialog, FormControl, TextInput, toast } from "frappe-ui"
import PageHeader from "@/components/PageHeader.vue"
import TreeTable from "@/components/TreeTable.vue"
import { insertDoc, runReport } from "@/api"
import { money, today } from "@/format"
import { can, currency, session } from "@/store"

const rows = ref<any[]>([])
const loading = ref(false)
const asOn = ref(today())
const query = ref("")
const collapsed = ref(new Set<string>())
const dialogOpen = ref(false)
const draft = reactive({ account_number: "", account_name: "", parent_account: "", is_group: false })
const fmt = (v: number) => money(v, currency.value)

const groups = computed(() => rows.value.filter((r) => r.is_group))
const allOpen = computed(() => collapsed.value.size === 0)

// a search keeps matching accounts and the groups above them
const visibleRows = computed(() => {
	const q = query.value.trim().toLowerCase()
	if (!q) return rows.value
	const keep = new Set<string>()
	const byName = new Map(rows.value.map((r) => [r.account, r]))
	for (const row of rows.value) {
		if (`${row.account_number || ""} ${row.account_name}`.toLowerCase().includes(q)) {
			for (let r = row; r; r = byName.get(r.parent_account)) keep.add(r.account)
		}
	}
	return rows.value.filter((r) => keep.has(r.account))
})

function groupLabel(row: any) {
	return `${"  ".repeat(row.indent || 0)}${row.account_number ? `${row.account_number} · ` : ""}${row.account_name}`
}

function toggle(name: string) {
	const next = new Set(collapsed.value)
	next.has(name) ? next.delete(name) : next.add(name)
	collapsed.value = next
}

function toggleAll() {
	collapsed.value = allOpen.value ? new Set(groups.value.filter((g) => g.indent >= 1).map((g) => g.account)) : new Set()
}

function openNew() {
	const indirect = groups.value.find((g) => g.account_name === "Indirect Expenses") || groups.value[0]
	Object.assign(draft, { account_number: "", account_name: "", parent_account: indirect?.account || "", is_group: false })
	dialogOpen.value = true
}

async function create() {
	if (!draft.account_number.trim() || !draft.account_name.trim()) {
		toast.error("Enter a number and a name")
		return
	}
	await insertDoc({ doctype: "Account", company: session.company, ...draft, is_group: draft.is_group ? 1 : 0 })
	dialogOpen.value = false
	toast.success(`Account ${draft.account_number} · ${draft.account_name} created`)
	await load()
}

function openDesk() {
	window.open(`/app/account/view/tree?company=${encodeURIComponent(session.company)}`, "_blank")
}

async function load() {
	loading.value = true
	try {
		const result = await runReport("Chart of Accounts", {
			company: session.company,
			as_on_date: asOn.value,
			root_type: "Expense",
			show_zero_balances: 1,
		})
		rows.value = result.result
	} finally {
		loading.value = false
	}
}

watch(asOn, load, { immediate: true })
</script>
