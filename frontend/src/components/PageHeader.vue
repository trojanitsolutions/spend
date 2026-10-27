<template>
	<div class="flex flex-wrap items-start justify-between gap-3 border-b border-outline-gray-1 px-4 py-4 sm:px-6">
		<div class="min-w-0">
			<RouterLink v-if="back" :to="back.to" class="mb-1 inline-flex items-center gap-1 text-sm text-ink-gray-5 hover:text-ink-gray-8">
				<span class="lucide-chevron-left size-3.5" aria-hidden="true" />{{ back.label }}
			</RouterLink>
			<div class="flex flex-wrap items-center gap-2">
				<h1 class="truncate text-xl font-semibold text-ink-gray-9">{{ title }}</h1>
				<slot name="badge" />
			</div>
			<p v-if="subtitle" class="mt-0.5 text-sm text-ink-gray-5">{{ subtitle }}</p>
		</div>
		<div class="flex flex-wrap items-center gap-2"><slot name="actions" /></div>
	</div>
</template>

<script setup lang="ts">
defineProps<{ title: string; subtitle?: string; back?: { to: string; label: string } }>()
</script>
