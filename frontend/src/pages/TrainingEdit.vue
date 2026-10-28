<template>
	<div>
		<PageHeader :title="form?.title || scenario" subtitle="Edit the scenario, its steps and its quiz" :back="{ to: '/training', label: 'Training' }">
			<template #actions>
				<Button icon-left="lucide-circle-dot" label="Record on the page" :disabled="!form" @click="record" />
				<Button variant="solid" label="Save" :loading="saving" :disabled="!form" @click="save" />
			</template>
		</PageHeader>

		<div v-if="!form" class="py-16 text-center"><LoadingText /></div>
		<form v-else class="mx-auto max-w-4xl space-y-6 p-4 sm:p-6" @submit.prevent="save">
			<fieldset class="grid grid-cols-1 gap-4 rounded-xl border border-outline-gray-1 p-4 sm:grid-cols-2">
				<legend class="px-1 text-base font-semibold">Scenario</legend>
				<FormControl v-model="form.track" type="select" label="Track" :options="form.tracks" />
				<FormControl v-model="form.difficulty" type="select" label="Difficulty" :options="['Beginner', 'Intermediate', 'Advanced']" />
				<FormControl v-model="form.start_route" label="Starts on" placeholder="/bills" />
				<FormControl v-model="form.passing_score" type="number" min="0" max="100" label="Passing score" />
				<FormControl v-model="form.video_url" class="sm:col-span-2" label="Intro video" placeholder="YouTube, Vimeo or a video file URL" />
				<FormControl v-model="form.description" class="sm:col-span-2" type="textarea" :rows="2" label="Description" />
				<div class="flex flex-wrap gap-x-6 gap-y-2 sm:col-span-2">
					<FormControl v-model="flags.is_active" type="checkbox" label="Active" />
					<FormControl v-model="flags.allow_guided" type="checkbox" label="Guided mode" />
					<FormControl v-model="flags.allow_practice" type="checkbox" label="Practice mode" />
				</div>
			</fieldset>

			<fieldset class="rounded-xl border border-outline-gray-1">
				<legend class="ml-4 px-1 text-base font-semibold">Steps</legend>
				<p v-if="!form.steps.length" class="px-4 py-6 text-center text-sm text-ink-gray-5">No steps yet. Record them on the page, or add one here.</p>
				<div v-for="(s, i) in form.steps" :key="i" class="border-b border-outline-gray-1 last:border-0">
					<div class="flex items-center gap-2 px-4 py-2">
						<span class="w-6 shrink-0 text-right text-sm tabular-nums text-ink-gray-5">{{ i + 1 }}</span>
						<button type="button" class="min-w-0 flex-1 truncate text-left text-base" @click="open = open === i ? -1 : i">
							{{ s.title || "Untitled step" }}
							<span class="ml-1 text-sm text-ink-gray-5">· {{ s.action_type }}{{ s.route ? ` on ${s.route}` : "" }}</span>
						</button>
						<span v-if="s.target_kind === 'Selector'" class="lucide-triangle-alert size-4 text-ink-amber-3" title="Fragile target: not a data-tour key" aria-label="Fragile target" />
						<Button variant="ghost" icon="lucide-arrow-up" aria-label="Move up" :disabled="i === 0" @click="move(form.steps, i, -1)" />
						<Button variant="ghost" icon="lucide-arrow-down" aria-label="Move down" :disabled="i === form.steps.length - 1" @click="move(form.steps, i, 1)" />
						<Button variant="ghost" icon="lucide-trash-2" aria-label="Delete step" @click="form.steps.splice(i, 1)" />
					</div>
					<div v-if="open === i" class="px-4 pb-4 sm:pl-12">
						<StepFields v-model="form.steps[i]" :scenario="scenario" />
					</div>
				</div>
				<div class="px-4 py-3">
					<Button icon-left="lucide-plus" label="Add step" @click="addStep" />
				</div>
			</fieldset>

			<fieldset class="space-y-4 rounded-xl border border-outline-gray-1 p-4">
				<legend class="px-1 text-base font-semibold">Quiz</legend>
				<p v-if="!form.quiz.length" class="text-sm text-ink-gray-5">Optional. The quiz is 30% of the score when there is one.</p>
				<div v-for="(q, i) in form.quiz" :key="i" class="grid grid-cols-1 gap-3 rounded-lg border border-outline-gray-2 p-3 sm:grid-cols-2">
					<FormControl v-model="q.question" class="sm:col-span-2" label="Question" />
					<FormControl v-model="q.options" type="textarea" :rows="3" label="Answers" description="One per line" />
					<div class="space-y-3">
						<FormControl v-model="q.correct_option" type="select" label="Correct answer" :options="['', ...lines(q.options)]" />
						<FormControl v-model="q.explanation" label="Explanation" placeholder="Shown after answering" />
					</div>
					<div class="flex justify-end sm:col-span-2">
						<Button variant="ghost" theme="red" icon-left="lucide-trash-2" label="Remove question" @click="form.quiz.splice(i, 1)" />
					</div>
				</div>
				<Button icon-left="lucide-plus" label="Add question" @click="form.quiz.push({ question: '', options: '', correct_option: '', explanation: '' })" />
			</fieldset>

			<fieldset class="space-y-2 rounded-xl border border-outline-gray-1 p-4">
				<legend class="px-1 text-base font-semibold">Sample data</legend>
				<p class="text-sm text-ink-gray-5">
					Created in the training company when missing, before the scenario starts. Allowed: Supplier, Item, Item Group, UOM, Cost Center, Expense Category, Project.
				</p>
				<FormControl v-model="form.seed_data" type="textarea" :rows="6" class="font-mono" placeholder='{"Supplier": [{"supplier_name": "Acme Stationers"}]}' />
			</fieldset>
		</form>
	</div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue"
import { useRoute, useRouter } from "vue-router"
import { Button, FormControl, LoadingText, toast } from "frappe-ui"
import PageHeader from "@/components/PageHeader.vue"
import { getScenarioForEdit, saveScenario, type EditableScenario } from "@/training/api"
import { blankStep, openRecorder } from "@/training/recorder"
import StepFields from "@/training/StepFields.vue"

const props = defineProps<{ scenario: string }>()
const route = useRoute()
const router = useRouter()
const form = ref<EditableScenario | null>(null)
const flags = reactive({ is_active: false, allow_guided: true, allow_practice: true })
const saving = ref(false)
const open = ref(-1)

onMounted(load)

async function load() {
	fill(await getScenarioForEdit(props.scenario))
}

function fill(data: EditableScenario) {
	form.value = data
	Object.assign(flags, {
		is_active: !!data.is_active,
		allow_guided: !!data.allow_guided,
		allow_practice: !!data.allow_practice,
	})
}

async function save() {
	if (!form.value) return
	saving.value = true
	try {
		const { tracks, name, title, ...values } = form.value
		fill(
			await saveScenario(props.scenario, {
				...values,
				is_active: flags.is_active ? 1 : 0,
				allow_guided: flags.allow_guided ? 1 : 0,
				allow_practice: flags.allow_practice ? 1 : 0,
			}),
		)
		toast.success("Scenario saved")
	} finally {
		saving.value = false
	}
}

function addStep() {
	const step = blankStep(route)
	step.route = form.value!.steps.at(-1)?.route || form.value!.start_route || ""
	form.value!.steps.push(step)
	open.value = form.value!.steps.length - 1
}

async function record() {
	await save()
	openRecorder(props.scenario, router)
}

function move<T>(list: T[], i: number, delta: number) {
	const [item] = list.splice(i, 1)
	list.splice(i + delta, 0, item)
	if (open.value === i) open.value = i + delta
}

function lines(text: string) {
	return (text || "").split("\n").map((l) => l.trim()).filter(Boolean)
}
</script>
