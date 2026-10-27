<template>
	<div>
		<PageHeader title="Notifications" subtitle="Approval requests and outcomes, budget alerts, bills due and recurring payments">
			<template #actions>
				<Button label="Mark all read" icon-left="lucide-check-check" :disabled="!counts.unread" @click="readAll" />
			</template>
		</PageHeader>

		<div class="flex flex-wrap gap-2 px-4 py-3 sm:px-6">
			<div class="max-w-full overflow-x-auto"><TabButtons v-model="filter" :options="FILTERS.map((f) => ({ label: f, value: f }))" /></div>
		</div>

		<div v-if="loading && !items.length" class="p-6"><LoadingText /></div>
		<EmptyState v-else-if="!shown.length" icon="lucide-bell-off" title="No notifications" message="You are all caught up." />
		<ul v-else class="divide-y divide-outline-gray-1 border-y border-outline-gray-1">
			<li v-for="n in shown" :key="n.name">
				<button type="button" class="flex w-full gap-3 px-4 py-3 text-left hover:bg-surface-gray-1 sm:px-6" @click="open(n)">
					<span :class="[TYPE_ICONS[n.type] || 'lucide-bell', 'mt-0.5 size-4 shrink-0', n.read ? 'text-ink-gray-4' : 'text-ink-gray-7']" aria-hidden="true" />
					<span class="min-w-0 flex-1">
						<span class="block text-base" :class="n.read ? 'text-ink-gray-6' : 'font-medium text-ink-gray-9'">{{ n.subject }}</span>
						<span v-if="n.email_content" class="mt-0.5 block text-sm text-ink-gray-5">{{ n.email_content }}</span>
						<span class="mt-0.5 block text-xs text-ink-gray-5">{{ n.type }} · {{ timeAgo(n.creation) }}</span>
					</span>
					<span v-if="!n.read" class="mt-1.5 size-2 shrink-0 rounded-full bg-surface-blue-3" aria-label="Unread" />
				</button>
			</li>
		</ul>
		<div v-if="items.length === limit" class="p-4 text-center"><Button label="Load more" @click="more" /></div>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import { Button, LoadingText, TabButtons } from "frappe-ui"
import EmptyState from "@/components/EmptyState.vue"
import PageHeader from "@/components/PageHeader.vue"
import { counts, getNotifications, markRead, notificationTarget, type SpendNotification, timeAgo, TYPE_ICONS } from "@/notifications"

const FILTERS = ["All", "Unread", "Approval", "Budget Alert", "Bill Reminder", "Recurring Payment"]

const router = useRouter()
const items = ref<SpendNotification[]>([])
const loading = ref(false)
const filter = ref("All")
const limit = ref(50)

const shown = computed(() => {
	if (filter.value === "All") return items.value
	if (filter.value === "Unread") return items.value.filter((n) => !n.read)
	return items.value.filter((n) => n.type === filter.value)
})

async function load() {
	loading.value = true
	try {
		items.value = await getNotifications(limit.value)
	} finally {
		loading.value = false
	}
}

function more() {
	limit.value += 50
	load()
}

async function readAll() {
	await markRead()
	items.value.forEach((n) => (n.read = 1))
}

async function open(n: SpendNotification) {
	if (!n.read) {
		n.read = 1
		markRead([n.name])
	}
	const target = notificationTarget(n)
	if (target.route) router.push(target.route)
	else if (target.href) window.open(target.href, "_blank")
}

onMounted(load)
</script>
