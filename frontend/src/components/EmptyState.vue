<template>
	<div class="flex flex-col items-center justify-center gap-3 px-4 py-16 text-center">
		<span v-if="icon" :class="[icon, 'size-8 text-ink-gray-4']" aria-hidden="true" />
		<h2 class="text-lg font-semibold text-ink-gray-8">{{ title }}</h2>
		<p v-if="message" class="max-w-md text-base text-ink-gray-5">{{ message }}</p>
		<div class="mt-2 flex gap-2"><slot /></div>
	</div>
</template>

<script setup lang="ts">
defineProps<{ title: string; message?: string; icon?: string }>()
</script>
