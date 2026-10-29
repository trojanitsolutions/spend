<template>
	<section class="card p-4 sm:px-6">
		<h2 class="mb-3 text-base font-semibold">Activity</h2>

		<form class="mb-5 space-y-2" @submit.prevent="send">
			<div class="relative">
				<label class="sr-only" for="activity-comment">Add a comment</label>
				<textarea
					id="activity-comment"
					ref="box"
					v-model="comment"
					rows="2"
					class="form-textarea w-full resize-y text-sm"
					placeholder="Add a comment… type @ to tag someone"
					role="combobox"
					aria-autocomplete="list"
					:aria-expanded="picking"
					aria-controls="activity-mentions"
					:aria-activedescendant="picking && matches.length ? `activity-mention-${active}` : undefined"
					@input="findQuery"
					@click="findQuery"
					@keyup.left="findQuery"
					@keyup.right="findQuery"
					@keydown="onKeydown"
					@blur="closeSoon"
				/>
				<Transition name="glass">
					<ul v-if="picking" id="activity-mentions" role="listbox" aria-label="People to tag" class="glass absolute left-0 top-full z-20 mt-2 w-72 max-w-full p-1.5">
						<li v-if="!matches.length" class="glass-empty px-3 py-2.5 text-sm">{{ users ? "No one to tag" : "Loading…" }}</li>
						<li
							v-for="(u, i) in matches"
							:id="`activity-mention-${i}`"
							:key="u.user"
							role="option"
							:aria-selected="i === active"
							class="glass-row flex min-h-11 cursor-pointer items-center gap-2.5 px-2.5 py-1.5"
							:class="{ 'is-active': i === active }"
							@mousedown.prevent="pick(u)"
							@mouseenter="active = i"
						>
							<Avatar size="md" :label="u.full_name || u.user" :image="u.user_image" />
							<div class="min-w-0">
								<div class="glass-title truncate text-[13px] font-medium leading-tight">{{ u.full_name || u.user }}</div>
								<div class="glass-subtitle truncate text-xs leading-tight">{{ u.user }}</div>
							</div>
						</li>
					</ul>
				</Transition>
			</div>
			<div class="flex justify-end gap-2">
				<Button variant="ghost" icon="lucide-at-sign" aria-label="Tag someone" title="Tag someone" @click="startTag" />
				<Button type="submit" variant="solid" label="Comment" :loading="sending" :disabled="!comment.trim()" />
			</div>
		</form>

		<div v-if="!timeline" class="py-2"><LoadingText /></div>
		<ol v-else class="relative space-y-4 before:absolute before:bottom-2 before:left-[11px] before:top-2 before:w-px before:bg-outline-gray-1">
			<li v-for="(e, i) in timeline" :key="i" class="relative flex gap-3">
				<span class="relative z-10 flex size-6 shrink-0 items-center justify-center rounded-full bg-surface-gray-2 ring-4 ring-surface-base">
					<span :class="[ICONS[e.type] || 'lucide-pencil', 'size-3.5 text-ink-gray-6']" aria-hidden="true" />
				</span>
				<div class="min-w-0 flex-1 pt-0.5">
					<div class="flex flex-wrap items-baseline gap-x-2 text-sm">
						<span class="font-medium text-ink-gray-8">{{ e.full_name }}</span>
						<span v-if="e.type !== 'Comment'" class="break-words text-ink-gray-6">{{ e.text }}</span>
						<span class="text-xs text-ink-gray-5" :title="fullDate(e.creation)">{{ timeAgo(e.creation) }}</span>
					</div>
					<p v-if="e.type === 'Comment'" class="mt-1 whitespace-pre-line break-words rounded-lg bg-surface-gray-2 px-3 py-2 text-sm text-ink-gray-8">
						<template v-for="(part, j) in pieces(e)" :key="j">
							<span v-if="part.user" class="whitespace-nowrap rounded bg-surface-blue-3 px-1 font-medium text-ink-blue-8" :title="part.user">{{ part.text }}</span>
							<template v-else>{{ part.text }}</template>
						</template>
					</p>
				</div>
			</li>
		</ol>
	</section>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue"
import { Avatar, Button, LoadingText } from "frappe-ui"
import { api, getMentionableUsers, type ActivityEntry, type MentionableUser } from "@/api"
import { timeAgo } from "@/notifications"

const props = defineProps<{ doctype: string; name: string; timeline?: ActivityEntry[] }>()
const emit = defineEmits<{ changed: [] }>()

const ICONS: Record<string, string> = {
	Created: "lucide-plus",
	Version: "lucide-pencil",
	Comment: "lucide-message-square",
	Workflow: "lucide-shield-check",
	Attachment: "lucide-paperclip",
	"Attachment Removed": "lucide-paperclip",
	Info: "lucide-info",
	Edit: "lucide-pencil",
}

const comment = ref("")
const sending = ref(false)
const box = ref<HTMLTextAreaElement | null>(null)

// ---- tagging: "@" opens a list of the people who can open this document

const users = ref<MentionableUser[] | null>(null)
const tagged = new Map<string, MentionableUser>() // "@Full Name" → user
const query = ref<string | null>(null)
const active = ref(0)
const picking = computed(() => query.value !== null)

const matches = computed(() => {
	const q = (query.value || "").toLowerCase()
	return (users.value || []).filter((u) => (u.full_name || "").toLowerCase().includes(q) || u.user.toLowerCase().includes(q)).slice(0, 6)
})
watch(matches, () => (active.value = 0))

watch(
	() => [props.doctype, props.name],
	() => {
		users.value = null
		tagged.clear()
	},
)

async function loadUsers() {
	if (users.value) return
	users.value = []
	try {
		users.value = await getMentionableUsers(props.doctype, props.name)
	} catch {
		users.value = null
	}
}

function findQuery() {
	const el = box.value
	if (!el) return
	const match = el.value.slice(0, el.selectionStart).match(/(?:^|\s)@([^\s@]*)$/)
	query.value = match ? match[1] : null
	if (match) loadUsers()
}

function pick(user: MentionableUser) {
	const el = box.value
	if (!el) return
	const label = `@${user.full_name || user.user}`
	const caret = el.selectionStart
	const start = el.value.slice(0, caret).lastIndexOf("@")
	comment.value = `${el.value.slice(0, start)}${label} ${el.value.slice(caret)}`
	tagged.set(label, user)
	query.value = null
	nextTick(() => {
		el.focus()
		el.setSelectionRange(start + label.length + 1, start + label.length + 1)
	})
}

function startTag() {
	const el = box.value
	if (!el) return
	const caret = el.selectionStart ?? comment.value.length
	const before = comment.value.slice(0, caret)
	const insert = before && !/\s$/.test(before) ? " @" : "@"
	comment.value = before + insert + comment.value.slice(caret)
	nextTick(() => {
		el.focus()
		el.setSelectionRange(caret + insert.length, caret + insert.length)
		findQuery()
	})
}

function onKeydown(event: KeyboardEvent) {
	if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
		event.preventDefault()
		send()
		return
	}
	if (!picking.value) return
	if (event.key === "Escape") {
		event.preventDefault()
		query.value = null
	} else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
		event.preventDefault()
		const n = matches.value.length
		if (n) active.value = (active.value + (event.key === "ArrowDown" ? 1 : n - 1)) % n
	} else if ((event.key === "Enter" || event.key === "Tab") && matches.value.length) {
		event.preventDefault()
		pick(matches.value[active.value])
	}
}

function closeSoon() {
	setTimeout(() => (query.value = null), 150)
}

async function send() {
	if (!comment.value.trim() || sending.value) return
	sending.value = true
	try {
		const mentions = [...tagged].filter(([label]) => comment.value.includes(label)).map(([, u]) => u.user)
		await api("spend.spend.activity.add_comment", { doctype: props.doctype, name: props.name, content: comment.value, mentions })
		comment.value = ""
		tagged.clear()
		emit("changed")
	} finally {
		sending.value = false
	}
}

// ---- timeline

/** A comment split into plain text and its "@Full Name" tags. */
function pieces(e: ActivityEntry): { text: string; user?: string }[] {
	const labels = new Map((e.mentions || []).map((m) => [`@${m.full_name || m.user}`, m.user]))
	if (!labels.size) return [{ text: e.text }]
	const escaped = [...labels.keys()].sort((a, b) => b.length - a.length).map((l) => l.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
	return e.text
		.split(new RegExp(`(${escaped.join("|")})`))
		.filter(Boolean)
		.map((text) => ({ text, user: labels.get(text) }))
}

function fullDate(value: string) {
	return new Date(value.replace(" ", "T")).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })
}
</script>

<style scoped>
/* The tag picker floats above the page, so it gets the regular glass material:
   blur and saturate what is behind it, a translucent fill, a hairline highlight. */
.glass {
	--glass-fill: rgb(255 255 255 / 0.72);
	--glass-edge: rgb(255 255 255 / 0.6);
	--glass-rim: rgb(0 0 0 / 0.08);
	--glass-title: rgb(0 0 0 / 0.85);
	--glass-subtitle: rgb(60 60 67 / 0.72);
	--glass-selected: var(--surface-blue-8, #0068d6);
	border-radius: 16px;
	background: var(--glass-fill);
	-webkit-backdrop-filter: blur(24px) saturate(1.5);
	backdrop-filter: blur(24px) saturate(1.5);
	border: 1px solid var(--glass-rim);
	box-shadow:
		inset 0 1px 0 var(--glass-edge),
		0 12px 32px -8px rgb(0 0 0 / 0.22),
		0 2px 6px rgb(0 0 0 / 0.08);
	transform-origin: top left;
}
[data-theme="dark"] .glass {
	--glass-fill: rgb(40 40 44 / 0.7);
	--glass-edge: rgb(255 255 255 / 0.12);
	--glass-rim: rgb(255 255 255 / 0.1);
	--glass-title: rgb(255 255 255 / 0.92);
	--glass-subtitle: rgb(235 235 245 / 0.62);
	--glass-selected: var(--surface-blue-6, #0a6fe0);
}
.glass-row {
	border-radius: 10px;
	transition: background-color 80ms ease-out;
}
.glass-title {
	color: var(--glass-title);
}
.glass-subtitle,
.glass-empty {
	color: var(--glass-subtitle);
}
/* the highlighted person reads like a selected menu item: accent fill, white text */
.glass-row.is-active {
	background: var(--glass-selected);
}
.glass-row.is-active .glass-title,
.glass-row.is-active .glass-subtitle {
	color: #fff;
}

.glass-enter-active {
	transition:
		opacity 140ms ease-out,
		transform 160ms cubic-bezier(0.2, 0.9, 0.3, 1.2);
}
.glass-leave-active {
	transition: opacity 100ms ease-in;
}
.glass-enter-from {
	opacity: 0;
	transform: scale(0.96) translateY(-4px);
}
.glass-leave-to {
	opacity: 0;
}

/* accessibility settings: solid surface, stronger edge, no movement */
@media (prefers-reduced-transparency: reduce) {
	.glass {
		-webkit-backdrop-filter: none;
		backdrop-filter: none;
		--glass-fill: rgb(250 250 252);
	}
	[data-theme="dark"] .glass {
		--glass-fill: rgb(36 36 40);
	}
}
@media (prefers-contrast: more) {
	.glass {
		-webkit-backdrop-filter: none;
		backdrop-filter: none;
		--glass-fill: rgb(255 255 255);
		--glass-rim: rgb(0 0 0 / 0.5);
		--glass-subtitle: rgb(0 0 0 / 0.75);
	}
	[data-theme="dark"] .glass {
		--glass-fill: rgb(20 20 22);
		--glass-rim: rgb(255 255 255 / 0.6);
		--glass-subtitle: rgb(255 255 255 / 0.8);
	}
}
@media (prefers-reduced-motion: reduce) {
	.glass-enter-active,
	.glass-leave-active,
	.glass-row {
		transition: none;
	}
	.glass-enter-from {
		transform: none;
	}
}
</style>
