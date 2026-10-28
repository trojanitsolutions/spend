<template>
	<div>
		<PageHeader title="Team progress" subtitle="Best result per person and scenario" :back="{ to: '/training', label: 'Training' }" />
		<div class="flex flex-wrap gap-3 px-4 pt-4 sm:px-6">
			<FormControl v-model="search" class="w-64" placeholder="Search people or scenarios" />
			<FormControl v-model="track" type="select" class="w-48" :options="[{ label: 'All tracks', value: '' }, ...tracks]" />
		</div>
		<DataTable class="p-4 sm:p-6" :columns="columns" :rows="filtered" row-key="key" :loading="loading" empty-text="Nobody has finished a scenario yet">
			<template #full_name="{ row }">
				<div class="font-medium text-ink-gray-9">{{ row.full_name }}</div>
				<div class="text-sm text-ink-gray-5">{{ row.user }}</div>
			</template>
			<template #passed="{ row }">
				<Badge :theme="row.passed ? 'green' : 'amber'" :label="row.passed ? 'Passed' : 'Needs practice'" />
			</template>
		</DataTable>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { Badge, FormControl } from "frappe-ui"
import DataTable, { type Column } from "@/components/DataTable.vue"
import PageHeader from "@/components/PageHeader.vue"
import { date } from "@/format"
import { getTeamProgress, type TeamRow } from "@/training/api"

const columns: Column[] = [
	{ key: "full_name", label: "Person" },
	{ key: "scenario", label: "Scenario" },
	{ key: "track", label: "Track" },
	{ key: "best_score", label: "Best score", align: "right" },
	{ key: "attempts", label: "Attempts", align: "right" },
	{ key: "passed", label: "Status" },
	{ key: "last_on", label: "Last attempt", format: (v) => date(v) },
]

const rows = ref<(TeamRow & { key: string })[]>([])
const loading = ref(true)
const search = ref("")
const track = ref("")

const tracks = computed(() => [...new Set(rows.value.map((r) => r.track))].sort())
const filtered = computed(() => {
	const q = search.value.trim().toLowerCase()
	return rows.value.filter(
		(r) =>
			(!track.value || r.track === track.value) &&
			(!q || `${r.full_name} ${r.user} ${r.scenario}`.toLowerCase().includes(q)),
	)
})

onMounted(async () => {
	try {
		const { rows: data } = await getTeamProgress()
		rows.value = data.map((r) => ({ ...r, key: `${r.user}|${r.scenario}` }))
	} finally {
		loading.value = false
	}
})
</script>
