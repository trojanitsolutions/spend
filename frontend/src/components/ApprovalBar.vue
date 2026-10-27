<template>
	<section v-if="info" class="rounded-xl border border-outline-gray-1 p-4">
		<div class="flex flex-wrap items-center gap-3">
			<span class="lucide-shield-check size-5 text-ink-gray-5" aria-hidden="true" />
			<div class="min-w-0 flex-1">
				<div class="flex flex-wrap items-center gap-2">
					<h2 class="text-base font-semibold">Approval</h2>
					<StatusBadge :status="info.state" />
				</div>
				<p class="mt-0.5 text-sm text-ink-gray-6">{{ hint }}</p>
			</div>
			<div class="flex flex-wrap gap-2">
				<Button
					v-for="action in info.actions"
					:key="action"
					:label="action"
					:variant="action === APPROVAL.reject || action === APPROVAL.revise ? 'subtle' : 'solid'"
					:theme="action === APPROVAL.reject ? 'red' : 'gray'"
					:loading="busy === action"
					@click="run(action)"
				/>
			</div>
		</div>

		<ol v-if="info.history.length" class="mt-4 space-y-2 border-t border-outline-gray-1 pt-3">
			<li v-for="(h, i) in info.history" :key="i" class="flex gap-2 text-sm">
				<span :class="[h.type === 'Workflow' ? 'lucide-circle-check' : 'lucide-message-square', 'mt-0.5 size-4 shrink-0 text-ink-gray-5']" aria-hidden="true" />
				<div class="min-w-0">
					<span class="font-medium text-ink-gray-8">{{ h.full_name }}</span>
					<span class="text-ink-gray-6"> · {{ h.type === "Workflow" ? `moved to ${h.content}` : h.content }}</span>
					<div class="text-xs text-ink-gray-5">{{ when(h.creation) }}</div>
				</div>
			</li>
		</ol>

		<Dialog v-model:open="rejecting" title="Reject" :actions="[{ label: 'Reject', variant: 'solid', theme: 'red', onClick: reject }]">
			<FormControl v-model="reason" type="textarea" label="Reason" required placeholder="What needs to change?" />
		</Dialog>
	</section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { Button, Dialog, FormControl, toast } from "frappe-ui"
import StatusBadge from "@/components/StatusBadge.vue"
import { api, applyAction, APPROVAL } from "@/api"

interface ApprovalInfo {
	state: string
	actions: string[]
	history: { type: string; content: string; full_name: string; creation: string }[]
}

const props = defineProps<{ doctype: string; name: string }>()
const emit = defineEmits<{ changed: [] }>()

const info = ref<ApprovalInfo | null>(null)
const busy = ref("")
const rejecting = ref(false)
const reason = ref("")

const HINTS: Record<string, string> = {
	Draft: "Send it for approval when it is ready. An Accounts Manager approves first, then the General Manager.",
	"Pending Manager Approval": "Waiting for an Accounts Manager.",
	"Pending GM Approval": "Approved by an Accounts Manager. Waiting for the General Manager.",
	Approved: "Approved by an Accounts Manager and the General Manager.",
	Rejected: "Rejected. Make the changes, then resubmit it.",
	Cancelled: "Cancelled after approval.",
}
const hint = computed(() => HINTS[info.value?.state || ""] || "")

async function load() {
	info.value = await api("spend.spend.approval.get_approval", { doctype: props.doctype, name: props.name })
}

async function run(action: string) {
	if (action === APPROVAL.reject) {
		reason.value = ""
		rejecting.value = true
		return
	}
	busy.value = action
	try {
		const result = await applyAction(props.doctype, props.name, action)
		toast.success(result.docstatus === 1 ? "Approved and posted" : `Now ${result.workflow_state}`)
		await load()
		emit("changed")
	} finally {
		busy.value = ""
	}
}

async function reject() {
	if (!reason.value.trim()) {
		toast.error("Give a reason for rejecting")
		return
	}
	busy.value = APPROVAL.reject
	try {
		await applyAction(props.doctype, props.name, APPROVAL.reject, reason.value)
		rejecting.value = false
		toast.success("Rejected")
		await load()
		emit("changed")
	} finally {
		busy.value = ""
	}
}

function when(value: string) {
	return new Date(value.replace(" ", "T")).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })
}

defineExpose({ load })
watch(() => props.name, load)
onMounted(load)
</script>
