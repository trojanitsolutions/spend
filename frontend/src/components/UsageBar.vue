<template>
	<div>
		<div v-if="label || caption" class="mb-1 flex justify-between gap-2 text-sm">
			<span class="truncate text-ink-gray-7">{{ label }}</span>
			<span class="shrink-0 tabular-nums text-ink-gray-5">{{ caption }}</span>
		</div>
		<div
			class="h-2 overflow-hidden rounded-full bg-surface-gray-2"
			role="progressbar"
			:aria-valuenow="Math.round(value)"
			aria-valuemin="0"
			aria-valuemax="100"
			:aria-label="label"
		>
			<div class="h-full rounded-full transition-all" :class="barClass" :style="{ width: `${Math.min(value, 100)}%` }" />
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed } from "vue"
import { utilizationTone } from "@/format"

const props = defineProps<{ value: number; label?: string; caption?: string; neutral?: boolean }>()

const barClass = computed(() => {
	if (props.neutral) return "bg-surface-gray-7"
	return { green: "bg-surface-green-3", amber: "bg-surface-amber-3", red: "bg-surface-red-5" }[utilizationTone(props.value)]
})
</script>
