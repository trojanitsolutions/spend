<template>
	<div>
		<PageHeader title="Training" subtitle="Learn Spend on the real pages, in a practice company">
			<template #actions>
				<template v-if="home?.is_trainer">
					<Button icon-left="lucide-users" label="Team progress" @click="$router.push('/training/team')" />
					<Button icon-left="lucide-rotate-ccw" label="Reset training data" :disabled="!home.training_company" @click="confirmReset" />
					<Button variant="solid" icon-left="lucide-plus" label="New scenario" @click="newOpen = true" />
				</template>
			</template>
		</PageHeader>

		<div v-if="state.run" class="mx-4 mt-4 flex flex-wrap items-center gap-3 rounded-xl border border-outline-blue-1 bg-surface-blue-1 px-4 py-3 sm:mx-6">
			<span class="lucide-graduation-cap size-5 text-ink-blue-3" aria-hidden="true" />
			<span class="flex-1 text-base">You are in the middle of <b>{{ state.run.scenario.title }}</b>.</span>
			<Button label="Exit training" @click="endRun" />
		</div>

		<div v-if="loading" class="py-16 text-center"><LoadingText /></div>
		<EmptyState
			v-else-if="!home?.tracks.length"
			icon="lucide-graduation-cap"
			title="No training yet"
			:message="home?.is_trainer ? 'Create a track in Desk, then add a scenario.' : 'Ask your trainer to give your role a training track.'"
		/>

		<div v-else class="space-y-6 p-4 sm:p-6">
			<section v-for="track in home!.tracks" :key="track.name" class="space-y-2">
				<div>
					<h2 class="text-lg font-semibold text-ink-gray-9">{{ track.title }}</h2>
					<p v-if="track.description" class="text-sm text-ink-gray-5">{{ track.description }}</p>
				</div>
				<p v-if="!track.scenarios.length" class="text-sm text-ink-gray-5">No scenarios in this track yet.</p>
				<ul class="divide-y divide-outline-gray-1 rounded-xl border border-outline-gray-1">
					<li v-for="s in track.scenarios" :key="s.name" class="flex flex-wrap items-center gap-3 px-4 py-3">
						<div class="min-w-0 flex-1">
							<div class="flex flex-wrap items-center gap-2">
								<span class="font-medium text-ink-gray-9">{{ s.title }}</span>
								<Badge :label="s.difficulty" />
								<Badge v-if="!s.is_active" theme="amber" label="Inactive" />
								<Badge v-if="s.best?.passed" theme="green" :label="`Passed · ${s.best.score}`" />
								<Badge v-else-if="s.best" theme="amber" :label="`Best ${s.best.score}`" />
							</div>
							<p v-if="s.description" class="mt-0.5 text-sm text-ink-gray-5">{{ s.description }}</p>
						</div>
						<div class="flex flex-wrap gap-2">
							<template v-if="home!.is_trainer">
								<Button variant="ghost" icon="lucide-pencil" aria-label="Edit scenario" title="Edit" @click="$router.push(`/training/${encodeURIComponent(s.name)}/edit`)" />
								<Button variant="ghost" icon="lucide-circle-dot" aria-label="Record steps" title="Record steps on the page" @click="record(s.name)" />
							</template>
							<Button v-for="mode in s.modes" :key="mode" :variant="mode === 'Guided' ? 'solid' : 'subtle'" :label="mode" :loading="starting === `${s.name}:${mode}`" @click="begin(s, mode)" />
						</div>
					</li>
				</ul>
			</section>
		</div>

		<Dialog v-model:open="introOpen" :title="intro?.scenario.title" size="2xl" :actions="[{ label: `Start ${intro?.mode}`, variant: 'solid', onClick: startIntro }]">
			<div v-if="intro" class="aspect-video overflow-hidden rounded-lg bg-surface-gray-2">
				<iframe v-if="embedUrl(intro.scenario.video_url)" :src="embedUrl(intro.scenario.video_url)!" class="size-full" allow="fullscreen; picture-in-picture" title="Intro video" />
				<video v-else :src="intro.scenario.video_url" controls class="size-full" />
			</div>
		</Dialog>

		<Dialog v-model:open="newOpen" title="New scenario" :actions="[{ label: 'Create', variant: 'solid', onClick: create }]">
			<form class="space-y-4" @submit.prevent="create">
				<FormControl v-model="draft.track" type="select" label="Track" :options="home?.tracks.map((t) => t.name) || []" required />
				<FormControl v-model="draft.title" label="Title" required placeholder="e.g. Pay a supplier" />
				<FormControl v-model="draft.start_route" label="Starts on" placeholder="/payments" description="The Spend page the trainee starts on" />
			</form>
		</Dialog>
	</div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue"
import { useRouter } from "vue-router"
import { Badge, Button, Dialog, FormControl, LoadingText, dialog, toast } from "frappe-ui"
import EmptyState from "@/components/EmptyState.vue"
import PageHeader from "@/components/PageHeader.vue"
import { errorMessage } from "@/api"
import { createScenario, getHome, resetTrainingData, type Home, type Mode, type ScenarioSummary } from "@/training/api"
import { openRecorder } from "@/training/recorder"
import { endRun, startRun, state } from "@/training/run"

const router = useRouter()
const home = ref<Home | null>(null)
const loading = ref(true)
const starting = ref("")
const intro = ref<{ scenario: ScenarioSummary; mode: Mode } | null>(null)
const introOpen = ref(false)
const newOpen = ref(false)
const draft = reactive({ track: "", title: "", start_route: "" })

onMounted(load)

async function load() {
	loading.value = true
	try {
		home.value = await getHome()
		draft.track ||= home.value.tracks[0]?.name || ""
	} finally {
		loading.value = false
	}
}

function begin(scenario: ScenarioSummary, mode: Mode) {
	if (scenario.video_url) {
		intro.value = { scenario, mode }
		introOpen.value = true
		return
	}
	start(scenario.name, mode)
}

function startIntro() {
	introOpen.value = false
	if (intro.value) start(intro.value.scenario.name, intro.value.mode)
}

async function start(name: string, mode: Mode) {
	starting.value = `${name}:${mode}`
	try {
		await startRun(name, mode, router)
	} catch (error) {
		toast.error(errorMessage(error))
	} finally {
		starting.value = ""
	}
}

function record(name: string) {
	endRun()
	openRecorder(name, router)
}

async function create() {
	if (!draft.track || !draft.title.trim()) {
		toast.error("Pick a track and enter a title")
		return
	}
	const { name } = await createScenario(draft.track, draft.title, draft.start_route)
	newOpen.value = false
	router.push(`/training/${encodeURIComponent(name)}/edit`)
}

function confirmReset() {
	dialog.confirm({
		title: "Reset training data?",
		message: `Every bill, payment, expense, asset, budget and project in ${home.value?.training_company} is cancelled and deleted. Real companies are not touched.`,
		confirmLabel: "Reset",
		onConfirm: async () => {
			const result = await resetTrainingData()
			if (result.failed.length) toast.warning(`Removed ${result.deleted} documents; ${result.failed.length} could not be removed`)
			else toast.success(`Removed ${result.deleted} training documents`)
		},
	})
}

/** YouTube and Vimeo links play in an iframe; anything else is treated as a video file. */
function embedUrl(url: string) {
	const youtube = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([\w-]{6,})/)
	if (youtube) return `https://www.youtube.com/embed/${youtube[1]}`
	const vimeo = url.match(/vimeo\.com\/(\d+)/)
	if (vimeo) return `https://player.vimeo.com/video/${vimeo[1]}`
	return null
}
</script>
