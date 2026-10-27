<template>
	<div>
		<PageHeader title="Tasks" subtitle="The work on each project. A project is completed when all its tasks are done.">
			<template #actions>
				<Button v-if="can('Task', 'create')" variant="solid" icon-left="lucide-plus" label="New Task" @click="openTask()" />
			</template>
		</PageHeader>

		<div class="grid grid-cols-2 gap-3 p-4 sm:px-6 lg:grid-cols-4">
			<StatCard label="Open" :value="count((r) => !DONE.includes(r.status))" />
			<StatCard label="Overdue" :value="count((r) => r.status === 'Overdue')" :tone="count((r) => r.status === 'Overdue') ? 'red' : undefined" />
			<StatCard label="Assigned to me" :value="count((r) => !DONE.includes(r.status) && assignees(r).includes(session.user))" />
			<StatCard label="Completed" :value="count((r) => r.status === 'Completed')" />
		</div>

		<div class="flex flex-wrap items-end gap-2 px-4 pb-2 sm:px-6">
			<div class="max-w-full overflow-x-auto"><TabButtons v-model="view" :options="VIEWS.map((v) => ({ label: v, value: v }))" /></div>
			<div class="w-full sm:ml-auto sm:w-56">
				<TextInput v-model="query" type="search" placeholder="Search tasks" :debounce="150">
					<template #prefix><span class="lucide-search size-4 text-ink-gray-5" aria-hidden="true" /></template>
				</TextInput>
			</div>
		</div>
		<FilterBar v-model="filters" :fields="FILTERS" />

		<DataTable :columns="columns" :rows="filtered" :loading="loading" clickable empty-text="No tasks match" @row-click="(r) => openTask(r.name)">
			<template #subject="{ row }">
				<div class="font-medium text-ink-gray-9">
					<span v-if="row.is_milestone" class="lucide-flag mr-1 inline-block size-3.5 text-ink-amber-3" aria-label="Milestone" />{{ row.subject }}
				</div>
				<div class="text-sm text-ink-gray-5">{{ row.name }}<template v-if="row.parent_task"> · under {{ row.parent_task }}</template></div>
			</template>
			<template #project="{ row }">
				<RouterLink :to="`/projects/${row.project}`" class="hover:underline" @click.stop>{{ row.project_name || row.project }}</RouterLink>
			</template>
			<template #status="{ value }"><StatusBadge :status="value" /></template>
		</DataTable>

	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { Button, TabButtons, TextInput } from "frappe-ui"
import DataTable, { type Column } from "@/components/DataTable.vue"
import FilterBar from "@/components/FilterBar.vue"
import PageHeader from "@/components/PageHeader.vue"
import StatCard from "@/components/StatCard.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import { getList } from "@/api"
import { type FilterField, toServerFilters, useListFilters } from "@/filters"
import { date, percent } from "@/format"
import { can, session } from "@/store"

const VIEWS = ["Open", "Mine", "Overdue", "Completed", "All"]
const DONE = ["Completed", "Cancelled"]

const FILTERS: FilterField[] = [
	{ key: "exp_end_date", label: "Due", type: "date-range" },
	{ key: "project", label: "Project", type: "link", doctype: "Project", filters: { company: session.company } },
	{ key: "status", label: "Status", type: "select", options: ["Open", "Working", "Pending Review", "Overdue", "Completed", "Cancelled"] },
	{ key: "priority", label: "Priority", type: "select", options: ["Low", "Medium", "High", "Urgent"] },
]

const router = useRouter()
const filters = useListFilters(FILTERS)
const rows = ref<any[]>([])
const loading = ref(true)
const view = ref("Open")
const query = ref("")

const columns: Column[] = [
	{ key: "subject", label: "Task" },
	{ key: "project", label: "Project" },
	{ key: "status", label: "Status" },
	{ key: "priority", label: "Priority" },
	{ key: "exp_end_date", label: "Due", format: (v) => (v ? date(v) : "—") },
	{ key: "progress", label: "Progress", align: "right", format: (v) => percent(v || 0, 0) },
	{ key: "_assign", label: "Assigned", format: (v) => JSON.parse(v || "[]").join(", ") || "—" },
]

const assignees = (r: any): string[] => JSON.parse(r._assign || "[]")
const count = (test: (r: any) => boolean) => rows.value.filter(test).length

const filtered = computed(() => {
	const q = query.value.trim().toLowerCase()
	return rows.value.filter((r) => {
		const shown =
			view.value === "All" ||
			(view.value === "Open" && !DONE.includes(r.status)) ||
			(view.value === "Mine" && !DONE.includes(r.status) && assignees(r).includes(session.user)) ||
			r.status === view.value
		return shown && (!q || `${r.subject} ${r.name}`.toLowerCase().includes(q))
	})
})

function openTask(name?: string) {
	router.push(name ? `/tasks/${name}` : { path: "/tasks/new", query: filters.project ? { project: filters.project } : {} })
}

async function load() {
	loading.value = true
	try {
		rows.value = await getList(
			"Task",
			["name", "subject", "project", "project.project_name as project_name", "status", "priority", "exp_end_date", "progress", "parent_task", "is_milestone", "_assign"],
			toServerFilters("Task", FILTERS, filters, { company: session.company }),
			"exp_end_date asc, creation desc",
			500,
		)
	} finally {
		loading.value = false
	}
}

onMounted(load)
watch(filters, load)
</script>
