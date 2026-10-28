<template>
	<Dialog :open="!!run" :title="title" :dismissible="false" @update:open="(v: boolean) => !v && close()">
		<div v-if="run" data-training-ui class="space-y-4">
			<!-- quiz -->
			<template v-if="stage === 'quiz'">
				<p class="text-sm text-ink-gray-6">A few questions before you finish.</p>
				<fieldset v-for="(q, i) in run.scenario.quiz" :key="i" class="space-y-1.5">
					<legend class="mb-1 text-base font-medium text-ink-gray-8">{{ i + 1 }}. {{ q.question }}</legend>
					<label v-for="option in q.options" :key="option" class="flex items-center gap-2 text-base text-ink-gray-7">
						<input v-model="answers[i]" type="radio" :name="`q${i}`" :value="option" class="border-outline-gray-3" />
						{{ option }}
					</label>
					<p v-if="quiz" class="text-sm" :class="quiz.results[i].correct ? 'text-ink-green-3' : 'text-ink-red-4'">
						{{ quiz.results[i].correct ? "Correct." : `The answer is: ${quiz.results[i].correct_option}.` }}
						<span class="text-ink-gray-6">{{ quiz.results[i].explanation }}</span>
					</p>
				</fieldset>
			</template>

			<!-- result -->
			<div v-else-if="stage === 'result' && result" class="space-y-3 text-center">
				<div class="text-4xl font-semibold tabular-nums">{{ result.score }}</div>
				<Badge :theme="result.status === 'Passed' ? 'green' : 'amber'" size="lg" :label="result.status" />
				<dl class="grid grid-cols-2 gap-2 pt-2 text-left text-sm sm:grid-cols-4">
					<div><dt class="text-ink-gray-5">Steps</dt><dd class="tabular-nums">{{ stepScore }}</dd></div>
					<div v-if="quiz"><dt class="text-ink-gray-5">Quiz</dt><dd class="tabular-nums">{{ quiz.score }}</dd></div>
					<div><dt class="text-ink-gray-5">Mistakes</dt><dd class="tabular-nums">{{ run.mistakes }}</dd></div>
					<div><dt class="text-ink-gray-5">Time</dt><dd class="tabular-nums">{{ duration }}</dd></div>
				</dl>
			</div>
			<div v-else class="py-6 text-center"><LoadingText text="Saving your result…" /></div>
		</div>
		<template #actions>
			<div data-training-ui class="flex flex-wrap justify-end gap-2">
				<template v-if="stage === 'quiz'">
					<Button v-if="!quiz" variant="solid" label="Check answers" :loading="busy" :disabled="answers.some((a) => !a)" @click="check" />
					<Button v-else variant="solid" label="See result" :loading="busy" @click="save" />
				</template>
				<template v-else-if="stage === 'result'">
					<Button label="Back to Training" @click="close('/training')" />
					<Button v-if="run?.scenario.next_scenario" variant="solid" label="Next scenario" @click="startNext" />
				</template>
			</div>
		</template>
	</Dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { Badge, Button, Dialog, LoadingText } from "frappe-ui"
import { checkQuiz, saveProgress, type QuizResult } from "./api"
import { elapsedSeconds, endRun, startRun, state, stepScore } from "./run"

const router = useRouter()
const run = computed(() => (state.run?.phase === "finish" ? state.run : null))
const stage = ref<"quiz" | "saving" | "result">("saving")
const answers = ref<string[]>([])
const quiz = ref<QuizResult | null>(null)
const result = ref<{ status: string; score: number } | null>(null)
const busy = ref(false)

const title = computed(() => (stage.value === "quiz" ? "Quick quiz" : `${run.value?.scenario.title ?? ""}: done`))
const duration = computed(() => {
	const s = elapsedSeconds()
	return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`
})

watch(
	() => run.value?.scenario.name,
	(name) => {
		if (!name) return
		quiz.value = null
		result.value = null
		answers.value = run.value!.scenario.quiz.map(() => "")
		if (run.value!.scenario.quiz.length) stage.value = "quiz"
		else save()
	},
	{ immediate: true },
)

async function check() {
	busy.value = true
	try {
		quiz.value = await checkQuiz(run.value!.scenario.name, answers.value)
	} finally {
		busy.value = false
	}
}

async function save() {
	const r = run.value
	if (!r) return
	busy.value = true
	stage.value = "saving"
	try {
		result.value = await saveProgress({
			scenario: r.scenario.name,
			mode: r.mode,
			step_score: stepScore.value,
			quiz_score: quiz.value ? quiz.value.score : null,
			hints_used: r.hints,
			mistakes: r.mistakes,
			time_taken: elapsedSeconds(),
		})
		stage.value = "result"
	} catch {
		stage.value = quiz.value ? "quiz" : "result"
	} finally {
		busy.value = false
	}
}

function close(to?: string) {
	endRun()
	if (to) router.push(to)
}

async function startNext() {
	const r = run.value!
	// keep the original company to return to; startRun reads it from the current run
	await startRun(r.scenario.next_scenario!, r.mode, router)
}
</script>
