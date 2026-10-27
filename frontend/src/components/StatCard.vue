<template>
	<div class="rounded-xl border border-outline-gray-1 bg-surface-base p-4">
		<div class="flex items-center gap-2 text-sm text-ink-gray-5">
			<span v-if="icon" :class="[icon, 'size-4']" aria-hidden="true" />{{ label }}
		</div>
		<div class="mt-2 text-2xl font-semibold tabular-nums" :class="toneClass">{{ value }}</div>
		<div v-if="hint || $slots.default" class="mt-1 text-sm text-ink-gray-5"><slot>{{ hint }}</slot></div>
	</div>
</template>

<script setup lang="ts">
import { computed } from "vue"

const props = defineProps<{ label: string; value: string | number; hint?: string; icon?: string; tone?: string }>()

const toneClass = computed(
	() =>
		({ red: "text-ink-red-4", amber: "text-ink-amber-4", green: "text-ink-green-4" } as Record<string, string>)[
			props.tone || ""
		] || "text-ink-gray-9",
)
</script>
