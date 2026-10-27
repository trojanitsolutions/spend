<template>
	<Popover v-model:open="open" align="end">
		<template #trigger>
			<button
				type="button"
				class="relative flex size-8 items-center justify-center rounded-md text-ink-gray-6 hover:bg-surface-gray-2"
				:aria-label="counts.unread ? `Notifications, ${counts.unread} unread` : 'Notifications'"
			>
				<span class="lucide-bell size-4" aria-hidden="true" />
				<span
					v-if="counts.unread"
					class="absolute -right-0.5 -top-0.5 min-w-4 rounded-full bg-surface-red-5 px-1 text-center text-[10px] font-semibold leading-4 text-white"
				>
					{{ counts.unread > 99 ? "99+" : counts.unread }}
				</span>
			</button>
		</template>
		<div class="w-80 max-w-[calc(100vw-2rem)]">
			<div class="flex items-center justify-between border-b border-outline-gray-1 px-3 py-2">
				<span class="text-base font-semibold">Notifications</span>
				<Button variant="ghost" size="sm" label="Mark all read" :disabled="!counts.unread" @click="readAll" />
			</div>
			<div v-if="loading && !items.length" class="p-4"><LoadingText /></div>
			<p v-else-if="!items.length" class="p-4 text-center text-sm text-ink-gray-5">You are all caught up.</p>
			<ul v-else class="max-h-96 divide-y divide-outline-gray-1 overflow-y-auto">
				<li v-for="n in items" :key="n.name">
					<button type="button" class="flex w-full gap-2 px-3 py-2.5 text-left hover:bg-surface-gray-1" @click="go(n)">
						<span :class="[TYPE_ICONS[n.type] || 'lucide-bell', 'mt-0.5 size-4 shrink-0 text-ink-gray-5']" aria-hidden="true" />
						<span class="min-w-0 flex-1">
							<span class="line-clamp-2 text-sm" :class="n.read ? 'text-ink-gray-6' : 'font-medium text-ink-gray-9'">{{ n.subject }}</span>
							<span class="text-xs text-ink-gray-5">{{ timeAgo(n.creation) }}</span>
						</span>
						<span v-if="!n.read" class="mt-1.5 size-2 shrink-0 rounded-full bg-surface-blue-3" aria-hidden="true" />
					</button>
				</li>
			</ul>
			<RouterLink to="/notifications" class="block border-t border-outline-gray-1 px-3 py-2 text-center text-sm text-ink-gray-7 hover:bg-surface-gray-1" @click="open = false">
				View all
			</RouterLink>
		</div>
	</Popover>
</template>

<script setup lang="ts">
import { ref, watch } from "vue"
import { useRouter } from "vue-router"
import { Button, LoadingText, Popover } from "frappe-ui"
import { counts, getNotifications, markRead, notificationTarget, type SpendNotification, timeAgo, TYPE_ICONS } from "@/notifications"

const router = useRouter()
const open = ref(false)
const loading = ref(false)
const items = ref<SpendNotification[]>([])

watch(open, async (isOpen) => {
	if (!isOpen) return
	loading.value = true
	try {
		items.value = await getNotifications(8)
	} finally {
		loading.value = false
	}
})

async function readAll() {
	await markRead()
	items.value.forEach((n) => (n.read = 1))
}

function go(n: SpendNotification) {
	open.value = false
	if (!n.read) markRead([n.name])
	const target = notificationTarget(n)
	if (target.route) router.push(target.route)
	else if (target.href) window.open(target.href, "_blank")
}
</script>
