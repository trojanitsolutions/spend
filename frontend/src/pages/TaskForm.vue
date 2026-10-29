<template>
	<div v-if="loading" class="p-6"><LoadingText /></div>
	<div v-else>
		<PageHeader :title="doc ? doc.subject : 'New Task'" :subtitle="subtitle" :back="back">
			<template v-if="doc" #badge><StatusBadge :status="doc.status" /></template>
			<template #actions>
				<template v-if="doc">
					<Button v-if="deskAccess" label="Open in Desk" icon-left="lucide-external-link" @click="openDesk" />
					<Button v-if="can('Task', 'write')" theme="red" label="Delete" @click="remove" />
					<Button v-if="canWrite && !DONE.includes(doc.status) && !doc.is_group" icon-left="lucide-check" label="Mark Completed" :loading="saving" @click="completeOpen = true" />
				</template>
				<Button v-if="canWrite" variant="solid" :label="doc ? 'Save' : 'Create Task'" :loading="saving" @click="save" />
			</template>
		</PageHeader>

		<CompleteTaskDialog v-if="doc" v-model:open="completeOpen" :tasks="[doc.name]" @done="load" />
		<DocLayout doctype="Task" :name="doc?.name" :version="doc?.modified">
			<form :class="doc ? 'space-y-6' : 'mx-auto max-w-3xl space-y-6'" @submit.prevent="save">
				<fieldset class="grid grid-cols-1 gap-4 card p-4 sm:grid-cols-2" :disabled="!canWrite">
					<legend class="px-1 text-base font-semibold">Task</legend>
					<FormControl v-model="draft.subject" class="sm:col-span-2" label="Subject" required placeholder="e.g. Pour the foundation" />
					<LinkField
						v-model="draft.project"
						doctype="Project"
						label="Project"
						required
						:filters="{ company: session.company, status: 'Open' }"
						:class="{ 'pointer-events-none opacity-60': !!doc }"
					/>
					<LinkField
						v-model="draft.parent_task"
						doctype="Task"
						label="Under group task"
						:filters="{ project: draft.project || '', is_group: 1, name: ['!=', name || ''] }"
					/>
					<FormControl v-model="draft.status" type="select" label="Status" :options="STATUSES" />
					<FormControl v-model="draft.priority" type="select" label="Priority" :options="PRIORITIES" />
					<div class="flex flex-col gap-2 sm:col-span-2 sm:flex-row sm:gap-6">
						<FormControl v-model="draft.is_group" type="checkbox" label="Group task (holds other tasks)" />
						<FormControl v-model="draft.is_milestone" type="checkbox" label="Milestone" />
					</div>
				</fieldset>

				<fieldset class="grid grid-cols-1 gap-4 card p-4 sm:grid-cols-2" :disabled="!canWrite">
					<legend class="px-1 text-base font-semibold">Timeline</legend>
					<FormControl v-model="draft.exp_start_date" type="date" label="Expected start" />
					<FormControl v-model="draft.exp_end_date" type="date" label="Expected end" />
					<FormControl v-model="draft.progress" type="number" label="% Progress" :disabled="draft.status === 'Completed'" />
					<FormControl
						v-if="draft.status === 'Completed'"
						v-model="draft.completed_on"
						type="date"
						label="Completed on"
						required
						:max="today()"
						:description="doc?.completed_by && doc.status === 'Completed' ? `Marked completed by ${doc.completed_by}` : 'When the work was done'"
					/>
				</fieldset>

				<fieldset class="space-y-4 card p-4" :disabled="!canWrite">
					<legend class="px-1 text-base font-semibold">Details</legend>
					<FormControl v-model="draft.description" type="textarea" label="Description" :rows="5" />
					<div>
						<div class="mb-1.5 text-xs text-ink-gray-5">Depends on — this task can be completed only after these are done</div>
						<div class="flex flex-wrap items-center gap-2">
							<Badge v-for="task in draft.depends_on" :key="task" theme="gray" class="cursor-pointer" :label="`${subjects[task] || task} ×`" @click="removeDependency(task)" />
							<LinkField
								:key="draft.depends_on.length"
								class="min-w-56 flex-1"
								doctype="Task"
								placeholder="Add a task this one waits for"
								:filters="{ project: draft.project || '', name: ['not in', [name || '', ...draft.depends_on]] }"
								@update:model-value="addDependency"
							/>
						</div>
					</div>
					<div>
						<div class="mb-1.5 text-xs text-ink-gray-5">Assigned to</div>
						<div class="flex flex-wrap items-center gap-2">
							<Badge v-for="user in draft.assign" :key="user" theme="blue" class="cursor-pointer" :label="`${user} ×`" @click="draft.assign = draft.assign.filter((u) => u !== user)" />
							<LinkField
								:key="draft.assign.length"
								class="min-w-56 flex-1"
								doctype="User"
								placeholder="Assign a user"
								:filters="{ enabled: 1, user_type: 'System User' }"
								@update:model-value="(u: string) => u && !draft.assign.includes(u) && draft.assign.push(u)"
							/>
						</div>
					</div>
				</fieldset>
			</form>
		</DocLayout>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { Badge, Button, FormControl, LoadingText, dialog, toast } from "frappe-ui"
import CompleteTaskDialog from "@/components/CompleteTaskDialog.vue"
import DocLayout from "@/components/DocLayout.vue"
import LinkField from "@/components/LinkField.vue"
import PageHeader from "@/components/PageHeader.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import { api, getDoc, insertDoc } from "@/api"
import { today } from "@/format"
import { can, deskAccess, session } from "@/store"

const STATUSES = ["Open", "Working", "Pending Review", "Overdue", "Completed", "Cancelled"]
const PRIORITIES = ["Low", "Medium", "High", "Urgent"]
const DONE = ["Completed", "Cancelled"]

// without `name` it is a new task; `?project=` and `?parent=` fill it in
const props = defineProps<{ name?: string }>()

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const completeOpen = ref(false)
const doc = ref<any>(null)
const assigned = ref<string[]>([])
const subjects = reactive<Record<string, string>>({})
const draft = reactive({
	subject: "",
	project: "",
	parent_task: "",
	status: "Open",
	priority: "Medium",
	exp_start_date: "",
	exp_end_date: "",
	progress: 0,
	is_group: false,
	is_milestone: false,
	completed_on: "",
	description: "",
	depends_on: [] as string[],
	assign: [] as string[],
})

const canWrite = computed(() => can("Task", doc.value ? "write" : "create"))
const fromProject = computed(() => route.query.from === "project" || (!props.name && !!route.query.project))
const back = computed(() => {
	const project = doc.value?.project || (route.query.project as string)
	return fromProject.value && project ? { to: `/projects/${project}`, label: "Project" } : { to: "/tasks", label: "Tasks" }
})
const subtitle = computed(() => {
	if (!doc.value) return "Track a piece of work on a project"
	return [doc.value.name, doc.value.project_name || doc.value.project, doc.value.parent_task && `under ${doc.value.parent_task}`].filter(Boolean).join(" · ")
})

async function load() {
	doc.value = null
	assigned.value = []
	Object.assign(draft, {
		subject: "",
		project: (route.query.project as string) || "",
		parent_task: (route.query.parent as string) || "",
		status: "Open",
		priority: "Medium",
		exp_start_date: "",
		exp_end_date: "",
		progress: 0,
		is_group: false,
		is_milestone: false,
		completed_on: "",
		description: "",
		depends_on: [],
		assign: [],
	})
	if (!props.name) return
	loading.value = true
	try {
		const d = await getDoc<any>("Task", props.name)
		d.project_name = await api("frappe.client.get_value", { doctype: "Project", filters: d.project, fieldname: "project_name" }, { silent: true })
			.then((r: any) => r?.project_name)
			.catch(() => "")
		doc.value = d
		assigned.value = JSON.parse(d._assign || "[]")
		for (const row of d.depends_on) subjects[row.task] = row.subject
		Object.assign(draft, {
			subject: d.subject,
			project: d.project,
			parent_task: d.parent_task || "",
			status: d.status,
			priority: d.priority || "Medium",
			exp_start_date: d.exp_start_date || "",
			exp_end_date: d.exp_end_date || "",
			progress: d.progress || 0,
			is_group: !!d.is_group,
			is_milestone: !!d.is_milestone,
			completed_on: d.completed_on || "",
			description: htmlToText(d.description),
			depends_on: d.depends_on.map((r: any) => r.task),
			assign: [...assigned.value],
		})
	} finally {
		loading.value = false
	}
}

// the Desk saves the description as HTML; this page edits it as plain text
function htmlToText(html?: string | null) {
	if (!html) return ""
	const el = document.createElement("div")
	el.innerHTML = html.replace(/<\/p>|<br\s*\/?>/g, "\n")
	return (el.textContent || "").trim()
}

function textToHtml(text: string) {
	const el = document.createElement("div")
	el.textContent = text
	return text ? `<p>${el.innerHTML.replace(/\n/g, "<br>")}</p>` : ""
}

async function addDependency(task: string) {
	if (!task || draft.depends_on.includes(task)) return
	draft.depends_on.push(task)
	if (!subjects[task]) subjects[task] = (await getDoc<any>("Task", task)).subject
}

function removeDependency(task: string) {
	draft.depends_on = draft.depends_on.filter((t) => t !== task)
}

async function save() {
	if (!draft.subject.trim() || !draft.project) {
		toast.error("Enter a subject and a project")
		return
	}
	const values = {
		subject: draft.subject.trim(),
		project: draft.project,
		parent_task: draft.parent_task || null,
		status: draft.status,
		priority: draft.priority,
		exp_start_date: draft.exp_start_date || null,
		exp_end_date: draft.exp_end_date || null,
		progress: Number(draft.progress) || 0,
		is_group: draft.is_group ? 1 : 0,
		is_milestone: draft.is_milestone ? 1 : 0,
		completed_on: draft.status === "Completed" ? draft.completed_on || today() : null,
		description: textToHtml(draft.description),
		depends_on: draft.depends_on.map((task) => ({ task })),
	}
	saving.value = true
	try {
		const isNew = !doc.value
		const saved = isNew
			? await insertDoc<{ name: string }>({ doctype: "Task", ...values })
			: await api<{ name: string }>("frappe.client.save", { doc: { ...doc.value, ...values } })
		await saveAssignments(saved.name)
		toast.success(isNew ? "Task created" : "Task saved")
		if (isNew) router.replace({ path: `/tasks/${saved.name}`, query: fromProject.value ? { from: "project" } : {} })
		else await load()
	} finally {
		saving.value = false
	}
}

async function saveAssignments(name: string) {
	const added = draft.assign.filter((u) => !assigned.value.includes(u))
	const removed = assigned.value.filter((u) => !draft.assign.includes(u))
	if (added.length) await api("frappe.desk.form.assign_to.add", { doctype: "Task", name, assign_to: added, description: draft.subject })
	for (const user of removed) await api("frappe.desk.form.assign_to.remove", { doctype: "Task", name, assign_to: user })
}

// picking Completed in the Status select asks for the date on the form
watch(
	() => draft.status,
	(status) => status === "Completed" && !draft.completed_on && (draft.completed_on = today()),
)

function remove() {
	dialog.confirm({
		title: "Delete task?",
		message: `${doc.value.subject} is deleted. Tasks under it or depending on it must be removed first.`,
		confirmLabel: "Delete",
		theme: "red",
		onConfirm: async () => {
			await api("frappe.client.delete", { doctype: "Task", name: props.name })
			toast.success("Task deleted")
			router.replace(back.value.to)
		},
	})
}

function openDesk() {
	window.open(`/app/task/${props.name}`, "_blank")
}

onMounted(load)
watch(() => props.name, load)
</script>
