<template>
	<div>
		<PageHeader title="Settings" subtitle="Approvals and notifications for everyone using Spend">
			<template #actions>
				<Button v-if="settings?.can_write" variant="solid" label="Save" :loading="saving" @click="save" />
			</template>
		</PageHeader>

		<div v-if="!settings" class="p-6"><LoadingText /></div>
		<form v-else class="mx-auto max-w-3xl space-y-6 p-4 sm:p-6" @submit.prevent="save">
			<fieldset class="space-y-3 card p-4" :disabled="!settings.can_write">
				<legend class="px-1 text-base font-semibold">Approvals</legend>
				<p class="text-sm text-ink-gray-6">
					Checked documents need the General Manager's approval before they are posted.
					A project can only be used once its budget is approved.
				</p>
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
					<FormControl v-for="[field, label] in APPROVALS" :key="field" v-model="values[field]" type="checkbox" :label="label" />
				</div>
				<FormControl v-model="values.allow_self_approval" type="checkbox" label="Allow approvers to approve documents they created" />
			</fieldset>

			<fieldset class="grid grid-cols-1 gap-4 card p-4 sm:grid-cols-2" :disabled="!settings.can_write">
				<legend class="px-1 text-base font-semibold">Alerts</legend>
				<FormControl v-model="values.budget_alert_threshold" type="number" min="0" max="100" label="Budget alert at (% used)" description="For project and cost center budgets. 0 turns it off." />
				<div class="space-y-3 pt-6">
					<FormControl v-model="values.notify_budget_exceeded" type="checkbox" label="Alert when a budget is exceeded" />
					<FormControl v-model="values.notify_recurring" type="checkbox" label="Alert when a recurring payment posts or fails" />
				</div>
				<FormControl v-model="values.notify_bills_due" type="checkbox" label="Daily reminder of bills to pay" />
				<FormControl v-if="values.notify_bills_due" v-model="values.bill_due_days" type="number" min="0" label="Include bills due within (days)" description="Overdue bills are always included" />
			</fieldset>

			<fieldset class="space-y-3 card p-4" :disabled="!settings.can_write">
				<legend class="px-1 text-base font-semibold">Email</legend>
				<FormControl v-model="values.send_email" type="checkbox" label="Also send notifications by email" />
				<p v-if="values.send_email && !settings.has_email_account" class="rounded-lg bg-surface-amber-1 p-3 text-sm text-ink-amber-4">
					No outgoing email account is set up, so emails are queued but not sent. Add one in Desk under Email Account.
				</p>
				<p class="text-sm text-ink-gray-6">People can turn email off for themselves in their Notification Settings in Desk.</p>
			</fieldset>

			<fieldset v-if="templates" class="space-y-3 card p-4">
				<legend class="px-1 text-base font-semibold">Appearance</legend>
				<p class="text-sm text-ink-gray-6">The look of Spend for everyone. Change a template's title, logo, colors and font in Desk.</p>
				<ul class="divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-1">
					<li v-for="t in templates" :key="t.name" class="flex flex-wrap items-center gap-3 px-3 py-2.5">
						<span
							class="size-5 shrink-0 rounded-full border border-outline-gray-2"
							:style="{ background: t.primary_color || 'var(--surface-gray-10)' }"
							aria-hidden="true"
						/>
						<div class="min-w-0 flex-1">
							<div class="flex items-center gap-2 text-base font-medium text-ink-gray-9">
								{{ t.name }}
								<Badge v-if="t.is_active" theme="green" label="Active" />
								<Badge v-if="t.is_standard" label="Standard" />
							</div>
							<div v-if="t.description" class="truncate text-sm text-ink-gray-5">{{ t.description }}</div>
						</div>
						<Button
							v-if="!t.is_active && can('Frontend Template', 'write')"
							type="button"
							label="Activate"
							:loading="activating === t.name"
							@click="activate(t.name)"
						/>
						<Button type="button" variant="ghost" icon="lucide-external-link" :aria-label="`Edit ${t.name} in Desk`" :href="deskLink(t.name)" />
					</li>
				</ul>
				<Button v-if="can('Frontend Template', 'create')" type="button" label="New template" icon-left="lucide-plus" href="/app/frontend-template/new" />
			</fieldset>

			<fieldset v-if="hasDemoData && can('Company', 'write')" class="space-y-3 card p-4">
				<legend class="px-1 text-base font-semibold">Demo data</legend>
				<p class="text-sm text-ink-gray-6">
					{{ session.company }} has the sample suppliers, items, bills, payments, expenses, budget, projects, assets and rent added at setup.
					Clearing cancels and deletes only those, with the entries posted for them. Records you added yourself stay.
				</p>
				<Button type="button" theme="red" label="Clear demo data" icon-left="lucide-trash-2" :loading="clearing" @click="confirmClear" />
			</fieldset>
		</form>
	</div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue"
import { Badge, Button, FormControl, LoadingText, dialog, toast } from "frappe-ui"
import PageHeader from "@/components/PageHeader.vue"
import { api } from "@/api"
import { can, hasDemoData, loadSession, reloadSession, session } from "@/store"
import { applyTheme } from "@/theme"

const APPROVALS = [
	["approve_purchase_invoice", "Bills"],
	["approve_supplier_payment", "Supplier payments"],
	["approve_journal_entry", "Expenses and journal entries"],
	["approve_recurring_payment", "Recurring payments"],
	["approve_budget", "Budgets"],
	["approve_project", "Projects"],
] as const

const CHECKS = [...APPROVALS.map(([f]) => f), "allow_self_approval", "notify_budget_exceeded", "notify_recurring", "notify_bills_due", "send_email"]

const settings = ref<any>(null)
const values = reactive<Record<string, any>>({})
const saving = ref(false)
const clearing = ref(false)
const templates = ref<any[] | null>(null)
const activating = ref("")

function apply(result: any) {
	settings.value = result
	for (const [key, value] of Object.entries(result.values)) values[key] = CHECKS.includes(key) ? Boolean(value) : value
}

async function save() {
	saving.value = true
	try {
		const payload = Object.fromEntries(Object.entries(values).map(([k, v]) => [k, typeof v === "boolean" ? Number(v) : v]))
		apply(await api("spend.api.save_settings", { values: payload }))
		await loadSession()
		toast.success("Settings saved")
	} finally {
		saving.value = false
	}
}

function confirmClear() {
	const company = session.company
	dialog.confirm({
		title: "Clear demo data?",
		message: `The demo records of ${company} are cancelled and deleted. This cannot be undone.`,
		confirmLabel: "Clear demo data",
		theme: "red",
		onConfirm: async () => {
			clearing.value = true
			try {
				const result = await api("spend.spend.demo.clear_company_demo_data", { company })
				if (result.failed.length) {
					const names = result.failed.slice(0, 3).map((f: { name: string }) => f.name).join(", ")
					toast.warning(`Removed ${result.deleted} demo records; ${result.failed.length} are still in use and stay (${names})`)
				} else toast.success(`Removed ${result.deleted} demo records from ${company}`)
				await reloadSession()
			} finally {
				clearing.value = false
			}
		},
	})
}

async function loadTemplates() {
	if (can("Frontend Template", "read")) templates.value = await api("spend.api.get_frontend_templates")
}

async function activate(name: string) {
	activating.value = name
	try {
		applyTheme(await api("spend.api.activate_frontend_template", { name }))
		await loadTemplates()
		toast.success(`${name} is now the active template`)
	} finally {
		activating.value = ""
	}
}

function deskLink(name: string) {
	return `/app/frontend-template/${encodeURIComponent(name)}`
}

onMounted(async () => {
	loadTemplates()
	apply(await api("spend.api.get_settings"))
})
</script>
