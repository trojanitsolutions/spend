<template>
	<!-- a large title bar that content scrolls under; its hairline shows once the page has scrolled -->
	<div
		ref="bar"
		class="bar-glass sticky top-0 z-10 flex flex-wrap items-end justify-between gap-3 border-b px-4 pb-3 pt-5 transition-colors sm:px-6"
		:class="scrolled ? 'border-outline-gray-1' : 'border-transparent'"
	>
		<div class="min-w-0">
			<RouterLink v-if="back" :to="back.to" class="mb-1 inline-flex items-center gap-0.5 text-[13px] font-medium text-[var(--accent-ink,var(--ink-gray-7))] hover:opacity-80">
				<span class="lucide-chevron-left size-4" aria-hidden="true" />{{ back.label }}
			</RouterLink>
			<div class="flex flex-wrap items-center gap-2">
				<h1 class="truncate text-[26px] font-bold leading-tight tracking-tight text-ink-gray-9">{{ title }}</h1>
				<slot name="badge" />
			</div>
			<p v-if="subtitle" class="mt-0.5 text-[13px] text-ink-gray-5">{{ subtitle }}</p>
		</div>
		<div class="flex flex-wrap items-center gap-2"><slot name="actions" /></div>
	</div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue"

defineProps<{ title: string; subtitle?: string; back?: { to: string; label: string } }>()

const bar = ref<HTMLElement>()
const scrolled = ref(false)
let scroller: HTMLElement | null = null

function onScroll() {
	scrolled.value = (scroller?.scrollTop ?? 0) > 0
}

onMounted(() => {
	scroller = bar.value?.closest("main") ?? null
	scroller?.addEventListener("scroll", onScroll, { passive: true })
	onScroll()
})
onBeforeUnmount(() => scroller?.removeEventListener("scroll", onScroll))
</script>
