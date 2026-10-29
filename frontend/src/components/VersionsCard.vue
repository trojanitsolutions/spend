<template>
	<div v-if="banner" class="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg p-3 text-sm" :class="banner.tone">
		<span :class="[banner.icon, 'size-4 shrink-0']" aria-hidden="true" />
		<span>{{ banner.text }}</span>
		<RouterLink v-if="banner.link" :to="banner.link.to" class="font-medium underline">{{ banner.link.label }}</RouterLink>
		<span v-if="banner.reason" class="text-ink-gray-6">· {{ banner.reason }}</span>
	</div>

	<section v-if="versions.length > 1" class="card">
		<h2 class="px-4 pt-4 text-base font-semibold sm:px-6">Versions</h2>
		<ol class="mt-2 divide-y divide-outline-gray-1">
			<li v-for="(v, i) in versions" :key="v.name" class="px-4 py-3 sm:px-6">
				<div class="flex flex-wrap items-center gap-x-3 gap-y-1">
					<span class="w-6 text-sm text-ink-gray-5">{{ i === 0 ? "v1" : `v${i + 1}` }}</span>
					<RouterLink v-if="v.name !== name" :to="routeOf(v)" class="font-medium text-ink-gray-9 hover:underline">{{ v.name }}</RouterLink>
					<span v-else class="font-medium text-ink-gray-9">{{ v.name }} <span class="font-normal text-ink-gray-5">(this)</span></span>
					<StatusBadge :status="stateOf(v)" />
					<span class="ml-auto tabular-nums text-ink-gray-8">{{ money(v.total, currency) }}</span>
					<span v-if="v.net_change != null" class="w-28 text-right text-sm tabular-nums text-ink-gray-6">
						{{ signed(v.net_change) }}
					</span>
				</div>
				<p v-if="v.reason" class="mt-1 pl-9 text-sm text-ink-gray-6">{{ v.reason }} — {{ v.owner_name }}</p>
				<details v-if="v.changes?.length" class="mt-1 pl-9 text-sm">
					<summary class="cursor-pointer text-ink-gray-6">{{ v.changes.length }} account {{ v.changes.length === 1 ? "change" : "changes" }}</summary>
					<table class="mt-2 w-full max-w-xl">
						<tbody>
							<tr v-for="c in v.changes" :key="c.account" class="border-t border-outline-gray-1">
								<td class="py-1 pr-3 text-ink-gray-8">{{ c.account }}</td>
								<td class="py-1 pr-3 text-right tabular-nums text-ink-gray-5">{{ c.before ? money(c.before, currency) : "new" }}</td>
								<td class="py-1 pr-3 text-right tabular-nums text-ink-gray-8">{{ c.after ? money(c.after, currency) : "removed" }}</td>
								<td class="py-1 text-right tabular-nums">{{ signed(c.change) }}</td>
							</tr>
						</tbody>
					</table>
				</details>
			</li>
		</ol>
	</section>
</template>

<script setup lang="ts">
import { computed } from "vue"
import StatusBadge from "@/components/StatusBadge.vue"
import type { Version } from "@/api"
import { money } from "@/format"

const props = defineProps<{ name: string; base: string; versions: Version[]; currency?: string }>()

const index = computed(() => props.versions.findIndex((v) => v.name === props.name))
const current = computed(() => props.versions[index.value])
const previous = computed(() => (index.value > 0 ? props.versions[index.value - 1] : null))
const next = computed(() => props.versions[index.value + 1] || null)

const banner = computed(() => {
	if (!current.value) return null
	if (current.value.docstatus === 2 && next.value) {
		const open = next.value.docstatus === 0
		return {
			tone: "bg-surface-gray-2 text-ink-gray-8",
			icon: "lucide-git-branch",
			text: open ? "Cancelled. Its amendment is waiting:" : "Cancelled and replaced by",
			link: { to: routeOf(next.value), label: next.value.name },
		}
	}
	if (current.value.docstatus === 2) {
		return { tone: "bg-surface-amber-1 text-ink-amber-4", icon: "lucide-ban", text: "Cancelled. Use Amend to make a corrected copy and send it for approval." }
	}
	if (previous.value) {
		return {
			tone: "bg-surface-blue-1 text-ink-blue-8",
			icon: "lucide-git-branch",
			text: "Amends",
			link: { to: routeOf(previous.value), label: previous.value.name },
			reason: current.value.reason,
		}
	}
	return null
})

function routeOf(v: Version) {
	return `/${props.base}/${v.name}`
}

function stateOf(v: Version) {
	if (v.docstatus === 2) return "Cancelled"
	if (v.docstatus === 0) return v.workflow_state || "Draft"
	return v.status || "Active"
}

function signed(value: number) {
	if (!value) return "±0"
	return `${value > 0 ? "+" : "−"}${money(Math.abs(value), props.currency)}`
}
</script>
