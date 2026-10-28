<template>
	<div>
		<PageHeader title="Approvals" subtitle="Documents waiting for your approval. The General Manager approves every document." />

		<div class="p-4 sm:p-6">
			<EmptyState
				v-if="!loading && !rows.length"
				icon="lucide-circle-check"
				title="Nothing to approve"
				:message="canApprove ? 'Documents sent for approval appear here.' : 'Only the General Manager approves documents.'"
			/>
			<DataTable v-else :columns="columns" :rows="rows" :loading="loading" clickable row-key="name" @row-click="open">
				<template #title="{ row }">
					<div class="max-w-72 truncate font-medium text-ink-gray-9">{{ row.title }}</div>
					<div class="text-sm text-ink-gray-5">{{ row.doctype }} · {{ row.name }}</div>
				<div v-if="row.note" class="max-w-96 truncate text-sm text-ink-blue-8" :title="row.note">{{ row.note }}</div>
				</template>
				<template #state="{ value }"><StatusBadge :status="value" /></template>
				<template #actions="{ row }">
					<div class="flex justify-end gap-2" @click.stop>
						<Button variant="subtle" theme="red" label="Reject" @click="startReject(row)" />
						<Button variant="solid" label="Approve" :loading="busy === row.name" @click="approve(row)" />
					</div>
				</template>
			</DataTable>
		</div>

		<Dialog v-model:open="rejecting" :title="`Reject ${target?.name || ''}`" :actions="[{ label: 'Reject', variant: 'solid', theme: 'red', onClick: reject }]">
			<FormControl v-model="reason" type="textarea" label="Reason" required placeholder="What needs to change?" />
		</Dialog>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import { Button, Dialog, FormControl, toast } from "frappe-ui"
import DataTable, { type Column } from "@/components/DataTable.vue"
import EmptyState from "@/components/EmptyState.vue"
import PageHeader from "@/components/PageHeader.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import { api, applyAction, APPROVAL } from "@/api"
import { money } from "@/format"
import { hasRole, session } from "@/store"
import { refreshCounts } from "@/notifications"

const router = useRouter()
const rows = ref<any[]>([])
const loading = ref(false)
const busy = ref("")
const rejecting = ref(false)
const reason = ref("")
const target = ref<any>(null)
const canApprove = computed(() => hasRole("General Manager"))

const columns: Column[] = [
	{ key: "title", label: "Document" },
	{ key: "owner_name", label: "Requested by" },
	{ key: "modified", label: "Waiting", format: (v) => age(v) },
	{ key: "state", label: "Stage" },
	{ key: "amount", label: "Amount", align: "right", format: (v, row) => money(v, row.currency) },
	{ key: "actions", label: "" },
]

function age(value: string) {
	const hours = Math.floor((Date.now() - Date.parse(value.replace(" ", "T"))) / 3600000)
	if (hours < 1) return "Just now"
	return hours < 24 ? `${hours} h` : `${Math.floor(hours / 24)} d`
}

async function load() {
	loading.value = true
	try {
		rows.value = await api("spend.spend.approval.get_pending_approvals", { company: session.company })
	} finally {
		loading.value = false
	}
}

function open(row: any) {
	router.push(row.route.replace(/^\/spend/, ""))
}

async function approve(row: any) {
	busy.value = row.name
	try {
		const result = await applyAction(row.doctype, row.name, APPROVAL.approve)
		toast.success(result.docstatus === 1 ? `${row.name} approved and posted` : `${row.name} approved`)
		await Promise.all([load(), refreshCounts()])
	} finally {
		busy.value = ""
	}
}

function startReject(row: any) {
	target.value = row
	reason.value = ""
	rejecting.value = true
}

async function reject() {
	if (!reason.value.trim()) {
		toast.error("Give a reason for rejecting")
		return
	}
	await applyAction(target.value.doctype, target.value.name, APPROVAL.reject, reason.value)
	rejecting.value = false
	toast.success(`${target.value.name} rejected`)
	await Promise.all([load(), refreshCounts()])
}

onMounted(load)
</script>
