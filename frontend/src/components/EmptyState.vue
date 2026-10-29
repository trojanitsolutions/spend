<template>
	<div class="flex flex-col items-center justify-center gap-3 px-4 py-16 text-center">
		<div v-if="icon" class="flex size-14 items-center justify-center rounded-full bg-surface-gray-2">
			<span :class="[icon, 'size-6 text-ink-gray-5']" aria-hidden="true" />
		</div>
		<h2 class="text-[17px] font-semibold tracking-tight text-ink-gray-9">{{ title }}</h2>
		<p v-if="message" class="max-w-sm text-[13px] leading-relaxed text-ink-gray-5">{{ message }}</p>
		<div class="mt-2 flex gap-2"><slot /></div>
	</div>
</template>

<script setup lang="ts">
defineProps<{ title: string; message?: string; icon?: string }>()
</script>
