<template>
	<!-- min-w-0 lets a grid column shrink below a long value; the value then scales its font to fit -->
	<div class="card min-w-0 p-4 [container-type:inline-size]">
		<div class="flex items-center gap-1.5 text-[13px] font-medium text-ink-gray-5">
			<span v-if="icon" :class="[icon, 'size-3.5']" aria-hidden="true" />{{ label }}
		</div>
		<div class="mt-1.5 whitespace-nowrap font-semibold leading-tight tracking-tight tabular-nums" :class="toneClass" :style="{ fontSize: valueSize }" :title="String(value)">{{ value }}</div>
		<div v-if="hint || $slots.default" class="mt-1 text-[13px] text-ink-gray-5"><slot>{{ hint }}</slot></div>
	</div>
</template>

<script setup lang="ts">
import { computed } from "vue"

const props = defineProps<{ label: string; value: string | number; hint?: string; icon?: string; tone?: string }>()

// 28px, or smaller so the value fits the card's width (a tabular digit is about 0.6em wide)
const valueSize = computed(() => `min(28px, calc(100cqi / ${Math.max(String(props.value).length, 1) * 0.6}))`)

const toneClass = computed(
	() =>
		({ red: "text-ink-red-4", amber: "text-ink-amber-4", green: "text-ink-green-4" } as Record<string, string>)[
			props.tone || ""
		] || "text-ink-gray-9",
)
</script>
