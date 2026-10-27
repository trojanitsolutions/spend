<template>
	<div>
		<div v-if="series.length > 1" class="mb-3 flex flex-wrap gap-4 text-sm text-ink-gray-6">
			<span v-for="(s, i) in series" :key="s.name" class="flex items-center gap-1.5">
				<span class="size-2.5 rounded-sm" :class="SERIES_CLASSES[i]" aria-hidden="true" />{{ s.name }}
			</span>
		</div>
		<div class="flex h-48 items-end gap-1.5 sm:gap-2" role="img" :aria-label="ariaLabel">
			<div v-for="(label, i) in labels" :key="label" class="flex h-full min-w-0 flex-1 flex-col justify-end">
				<div class="flex flex-1 items-end justify-center gap-0.5">
					<div
						v-for="(s, j) in series"
						:key="s.name"
						class="group relative w-full max-w-8 rounded-t-sm transition-opacity hover:opacity-80"
						:class="SERIES_CLASSES[j]"
						:style="{ height: `${max ? (Math.max(s.values[i], 0) / max) * 100 : 0}%`, minHeight: s.values[i] > 0 ? '2px' : '0' }"
						:title="`${label} · ${s.name}: ${format(s.values[i])}`"
					/>
				</div>
				<div class="mt-1.5 truncate text-center text-xs text-ink-gray-5">{{ label }}</div>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed } from "vue"

const SERIES_CLASSES = ["bg-surface-gray-4", "bg-surface-blue-3", "bg-surface-amber-3"]

const props = defineProps<{
	labels: string[]
	series: { name: string; values: number[] }[]
	format?: (value: number) => string
}>()

const format = (v: number) => (props.format ? props.format(v) : String(v))
const max = computed(() => Math.max(0, ...props.series.flatMap((s) => s.values)))
const ariaLabel = computed(() =>
	props.labels.map((l, i) => `${l}: ${props.series.map((s) => `${s.name} ${format(s.values[i])}`).join(", ")}`).join("; "),
)
</script>
