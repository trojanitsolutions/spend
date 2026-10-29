<template>
	<div>
		<PageHeader title="Reports" subtitle="All figures come from posted ledger entries" />
		<div class="space-y-8 p-4 sm:p-6">
			<section v-for="group in groups" :key="group">
				<h2 class="mb-3 text-sm font-medium uppercase tracking-wide text-ink-gray-5">{{ group }}</h2>
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
					<RouterLink
						v-for="r in reports.filter((r) => r.group === group)"
						:key="r.slug"
						:to="`/reports/${r.slug}`"
						class="group card p-4 transition-colors hover:border-outline-gray-3 hover:bg-surface-gray-1"
					>
						<span :class="[r.icon, 'size-5 text-ink-gray-6']" aria-hidden="true" />
						<div class="mt-3 font-medium text-ink-gray-9">{{ r.name.replace(' Report', '') }}</div>
						<p class="mt-1 text-sm text-ink-gray-5">{{ r.description }}</p>
					</RouterLink>
				</div>
			</section>
		</div>
	</div>
</template>

<script setup lang="ts">
import PageHeader from "@/components/PageHeader.vue"
import { computed } from "vue"
import { REPORTS } from "@/reports"
import { canRunReport } from "@/store"

const GROUPS = ["Assets", "Budgets & Spending", "Projects", "Purchasing", "Accounting"] as const

// only the reports the user's roles allow, and only the groups that still hold one
const reports = computed(() => REPORTS.filter((r) => canRunReport(r.name)))
const groups = computed(() => GROUPS.filter((group) => reports.value.some((r) => r.group === group)))
</script>
