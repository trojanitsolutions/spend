import { computed, onBeforeUnmount, onMounted, reactive, watch } from "vue"
import { useRoute, useRouter, type RouteLocationNormalizedLoaded, type Router } from "vue-router"
import { reloadSession, session, setCompany } from "@/store"
import { getScenario, startTraining, type Mode, type Scenario, type Step } from "./api"
import { matches } from "./expect"
import { findTarget, readValue } from "./tour"

const STORAGE_KEY = "spend:training-run"
const MISTAKE_POINTS = 5
const HINT_POINTS = 15
// a value must stay put this long before it counts: the trainee may still be typing
const SETTLE_MS = 1200
const TICK_MS = 250

interface Run {
	scenario: Scenario
	mode: Mode
	index: number
	hints: number
	mistakes: number
	startedAt: number
	finishedAt: number
	/** Practice: the current step's hint and highlight are shown */
	hintRevealed: boolean
	/** the company to go back to when the run ends */
	previousCompany: string
	phase: "steps" | "finish"
}

export const state = reactive({ run: readStored() as Run | null })

export const step = computed<Step | undefined>(() =>
	state.run?.phase === "steps" ? state.run.scenario.steps[state.run.index] : undefined,
)
export const showCoach = computed(() => state.run?.mode === "Guided" || !!state.run?.hintRevealed)

export const stepScore = computed(() => {
	const run = state.run
	if (!run) return 0
	const hintCost = run.mode === "Practice" ? run.hints * HINT_POINTS : 0
	return Math.max(0, 100 - run.mistakes * MISTAKE_POINTS - hintCost)
})

export function elapsedSeconds() {
	const run = state.run
	return run ? Math.round(((run.finishedAt || Date.now()) - run.startedAt) / 1000) : 0
}

/** Whether the current page is where the step happens: the same path, or the same route pattern. */
export function isOnStepRoute(route: RouteLocationNormalizedLoaded, stepRoute: string) {
	if (!stepRoute) return true
	return stepRoute === route.path || stepRoute === route.matched.at(-1)?.path
}

// ── Starting and ending ────────────────────────────────────────────

/** Switch to the training company, open the scenario's first page, and start the coach. */
export async function startRun(name: string, mode: Mode, router: Router) {
	const scenario = await getScenario(name)
	if (!scenario.steps.length) throw new Error("This scenario has no steps yet")
	const { company } = await startTraining(name)
	const previousCompany = state.run?.previousCompany || session.company
	if (!session.companies.some((c) => c.name === company)) await reloadSession()
	setCompany(company)
	state.run = {
		scenario,
		mode,
		index: 0,
		hints: 0,
		mistakes: 0,
		startedAt: Date.now(),
		finishedAt: 0,
		hintRevealed: false,
		previousCompany,
		phase: "steps",
	}
	const first = scenario.start_route || scenario.steps[0].route
	if (first && !first.includes(":")) await router.push(first)
}

/** Leave training: back to the company the user was in before. */
export function endRun() {
	const previous = state.run?.previousCompany
	state.run = null
	if (previous && previous !== session.company && session.companies.some((c) => c.name === previous)) {
		setCompany(previous)
	}
}

export function next() {
	const run = state.run
	if (!run || run.phase !== "steps") return
	if (run.index + 1 >= run.scenario.steps.length) {
		run.finishedAt = Date.now()
		run.phase = "finish"
		return
	}
	run.index += 1
	run.hintRevealed = false
}

export function useHint() {
	const run = state.run
	if (!run || run.hintRevealed) return
	run.hints += 1
	run.hintRevealed = true
}

// ── Following the trainee ──────────────────────────────────────────

/**
 * Watches the real page and moves the run along. Mount once, in the app shell.
 *
 * A Click step is done when its target is clicked. An Enter Value or Select
 * Option step is done when the target's value matches the Expected Value, or,
 * without one, when something new was entered. A value that settles on the
 * wrong answer counts as one mistake.
 */
export function useRunEngine() {
	const route = useRoute()
	const router = useRouter()

	// per step; reset when the step changes
	let initial: string | null = null
	let interacted = false
	let lastValue: string | null = null
	let lastChangeAt = 0
	let judged = new Set<string>()

	function resetStep() {
		initial = null
		interacted = false
		lastValue = null
		lastChangeAt = 0
		judged = new Set()
	}

	function target() {
		const s = step.value
		return s ? findTarget(s.target, s.target_kind) : null
	}

	function onClick(event: Event) {
		const s = step.value
		if (!s || isTrainingUi(event.target)) return
		const el = target()
		if (!el || !el.contains(event.target as Node)) return
		interacted = true
		// let the page's own handler (a navigation, a dialog) run first
		if (s.action_type === "Click") window.setTimeout(next, 60)
	}

	function onInput(event: Event) {
		const el = target()
		if (el && el.contains(event.target as Node)) interacted = true
	}

	function tick() {
		const s = step.value
		if (!s || s.action_type === "Click" || s.action_type === "Observe") return
		if (!isOnStepRoute(route, s.route)) return
		const el = target()
		if (!el) return
		const value = readValue(el).trim()
		const now = Date.now()
		if (initial === null) initial = value
		if (value !== lastValue) {
			lastValue = value
			lastChangeAt = now
			if (value !== initial) interacted = true
		}
		if (s.expected_value) {
			if (matches(value, s.expected_value) && (interacted || value !== initial)) next()
			else if (value && value !== initial && now - lastChangeAt > SETTLE_MS && !judged.has(value)) {
				judged.add(value)
				state.run!.mistakes += 1
			}
		} else if (value && value !== initial && now - lastChangeAt > SETTLE_MS) {
			next()
		}
	}

	let timer: ReturnType<typeof setInterval> | undefined
	onMounted(() => {
		// capture: see the click even when a component stops it from bubbling
		document.addEventListener("click", onClick, true)
		document.addEventListener("input", onInput, true)
		document.addEventListener("change", onInput, true)
		timer = setInterval(tick, TICK_MS)
	})
	onBeforeUnmount(() => {
		document.removeEventListener("click", onClick, true)
		document.removeEventListener("input", onInput, true)
		document.removeEventListener("change", onInput, true)
		clearInterval(timer)
	})

	watch(() => [state.run?.scenario.name, state.run?.index], resetStep)
	watch(() => state.run, persist, { deep: true })

	// the run belongs to the training company; switching away by hand ends it
	watch(
		() => session.company,
		(company) => {
			if (state.run && company && !session.companies.find((c) => c.name === company)?.is_training) endRun()
		},
	)

	function goToStep() {
		const s = step.value
		if (s?.route && !s.route.includes(":")) router.push(s.route)
	}

	return { route, goToStep }
}

/** The coach, the recorder and their dialogs carry this, so using them isn't using the page. */
export function isTrainingUi(node: EventTarget | null) {
	return node instanceof Element && !!node.closest("[data-training-ui]")
}

function persist(run: Run | null) {
	try {
		if (run) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(run))
		else sessionStorage.removeItem(STORAGE_KEY)
	} catch {
		// storage can be unavailable; a reload then just ends the run
	}
}

function readStored(): Run | null {
	try {
		const raw = sessionStorage.getItem(STORAGE_KEY)
		return raw ? (JSON.parse(raw) as Run) : null
	} catch {
		return null
	}
}
