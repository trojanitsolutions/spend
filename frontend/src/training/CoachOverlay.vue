<template>
	<div v-if="run && current" class="pointer-events-none fixed inset-0 z-[60]">
		<!-- dimming would also darken a field's dropdown, which opens outside the target -->
		<div v-if="showCoach && rect" class="coach-spotlight" :class="{ 'coach-dim': dims }" :style="spotlightStyle" />

		<!-- Practice: only a progress pill until the trainee asks for a hint -->
		<div
			v-if="!showCoach"
			data-training-ui
			class="pointer-events-auto fixed bottom-4 right-4 flex items-center gap-2 rounded-full border border-outline-gray-2 bg-surface-base py-1 pl-3 pr-1 text-sm text-ink-gray-7 shadow-xl"
		>
			<span class="tabular-nums">Practice · step {{ run.index + 1 }} of {{ total }}</span>
			<Button size="sm" icon-left="lucide-lightbulb" label="Hint" @click="useHint" />
			<Button size="sm" variant="ghost" icon="lucide-x" aria-label="Exit training" @click="exit" />
		</div>

		<div
			v-else
			ref="card"
			data-training-ui
			class="pointer-events-auto fixed rounded-xl border border-outline-gray-2 bg-surface-base p-4 text-ink-gray-8 shadow-2xl"
			:class="cardPos ? '' : 'coach-card-docked'"
			:style="cardStyle"
			role="dialog"
			aria-live="polite"
			:aria-label="current.title"
		>
			<div class="mb-1 flex items-center justify-between text-xs text-ink-gray-5">
				<span class="tabular-nums">Step {{ run.index + 1 }} of {{ total }}</span>
				<span class="flex items-center gap-1">
					{{ run.mode }}
					<button type="button" class="rounded p-0.5 hover:bg-surface-gray-2" aria-label="Exit training" title="Exit training" @click="exit">
						<span class="lucide-x size-3.5" aria-hidden="true" />
					</button>
				</span>
			</div>
			<div class="mb-3 h-1 overflow-hidden rounded bg-surface-gray-2">
				<div class="h-full rounded bg-surface-gray-7 transition-all" :style="{ width: `${((run.index + 1) / total) * 100}%` }" />
			</div>

			<h3 class="mb-1 text-base font-semibold">{{ current.title }}</h3>
			<!-- Text Editor HTML is sanitized by Frappe when the scenario is saved -->
			<div v-if="current.body" class="coach-body text-sm leading-relaxed text-ink-gray-7" v-html="current.body" />

			<p v-if="current.hint" class="mt-2 rounded bg-surface-amber-2 px-2 py-1.5 text-sm text-ink-amber-4">{{ current.hint }}</p>

			<div v-if="!onRoute" class="mt-2 rounded bg-surface-gray-2 px-2 py-1.5 text-sm text-ink-gray-7">
				This step is on <b>{{ current.route }}</b>.
				<button v-if="!current.route.includes(':')" type="button" class="ml-1 underline" @click="goToStep">Take me there</button>
			</div>
			<p v-else-if="lost && current.action_type !== 'Observe'" class="mt-2 rounded bg-surface-gray-2 px-2 py-1.5 text-sm text-ink-gray-7">
				Look for <b>{{ current.target_label || current.target }}</b> on this page.
			</p>

			<div class="mt-4 flex items-center justify-end gap-2">
				<Button v-if="current.action_type === 'Observe'" label="Next" variant="solid" icon-right="lucide-arrow-right" @click="next" />
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { Button } from "frappe-ui"
import { endRun, isOnStepRoute, next, showCoach, state, step, useHint, useRunEngine } from "./run"
import { findTarget } from "./tour"

const CARD_WIDTH = 340
const GAP = 14
const MARGIN = 12
// how long the target may be missing before the coach describes it
const LOST_AFTER_MS = 2000

const { route, goToStep } = useRunEngine()

const run = computed(() => state.run)
const current = step
const total = computed(() => run.value?.scenario.steps.length ?? 0)
const dims = computed(() => current.value?.action_type === "Click" || current.value?.action_type === "Observe")
const onRoute = computed(() => !current.value || isOnStepRoute(route, current.value.route))

const rect = ref<DOMRect | null>(null)
const card = ref<HTMLElement | null>(null)
const cardPos = ref<{ top: number; left: number } | null>(null)
const lost = ref(false)
let missingSince = 0
let frame = 0

// follow the target every frame: pages scroll, dialogs open, panels resize
function track() {
	const s = current.value
	const el = s && onRoute.value ? findTarget(s.target, s.target_kind) : null
	const next = el ? el.getBoundingClientRect() : null
	rect.value = next && next.width + next.height > 0 ? next : null
	if (rect.value || !s) missingSince = 0
	else missingSince ||= Date.now()
	lost.value = !!missingSince && Date.now() - missingSince > LOST_AFTER_MS
	placeCard()
	frame = requestAnimationFrame(track)
}

function placeCard() {
	const vw = window.innerWidth
	const vh = window.innerHeight
	const h = card.value?.offsetHeight ?? 200
	const w = Math.min(CARD_WIDTH, vw - MARGIN * 2)
	const r = rect.value
	if (vw < 640) {
		cardPos.value = null
		return
	}
	if (!r) {
		cardPos.value = cornerAwayFrom(r, w, h, vw, vh)
		return
	}
	const clampLeft = (x: number) => Math.min(Math.max(x, MARGIN), vw - w - MARGIN)
	const clampTop = (y: number) => Math.min(Math.max(y, MARGIN), vh - h - MARGIN)
	if (r.bottom + GAP + h < vh - MARGIN) cardPos.value = { top: r.bottom + GAP, left: clampLeft(r.left) }
	else if (r.top - GAP - h > MARGIN) cardPos.value = { top: r.top - GAP - h, left: clampLeft(r.left) }
	else if (r.right + GAP + w < vw - MARGIN) cardPos.value = { top: clampTop(r.top), left: r.right + GAP }
	else if (r.left - GAP - w > MARGIN) cardPos.value = { top: clampTop(r.top), left: r.left - GAP - w }
	else cardPos.value = cornerAwayFrom(r, w, h, vw, vh)
}

/** A screen corner for the card that doesn't cover the element the step needs. */
function cornerAwayFrom(r: DOMRect | null, w: number, h: number, vw: number, vh: number) {
	const corners = [
		{ top: vh - h - MARGIN, left: vw - w - MARGIN },
		{ top: vh - h - MARGIN, left: MARGIN },
		{ top: MARGIN, left: vw - w - MARGIN },
		{ top: MARGIN, left: MARGIN },
	]
	if (!r) return corners[0]
	const overlaps = (c: { top: number; left: number }) =>
		c.left < r.right + GAP && c.left + w > r.left - GAP && c.top < r.bottom + GAP && c.top + h > r.top - GAP
	return corners.find((c) => !overlaps(c)) ?? corners[0]
}

// bring each new target into view once
watch(
	() => [run.value?.index, showCoach.value, route.path],
	() =>
		window.setTimeout(() => {
			const s = current.value
			if (s && showCoach.value) findTarget(s.target, s.target_kind)?.scrollIntoView({ block: "center", behavior: "smooth" })
		}, 150),
	{ immediate: true },
)

onMounted(() => (frame = requestAnimationFrame(track)))
onBeforeUnmount(() => cancelAnimationFrame(frame))

function exit() {
	endRun()
}

const spotlightStyle = computed(() => {
	const r = rect.value
	if (!r) return {}
	const pad = 6
	return { top: `${r.top - pad}px`, left: `${r.left - pad}px`, width: `${r.width + pad * 2}px`, height: `${r.height + pad * 2}px` }
})

const cardStyle = computed(() =>
	cardPos.value ? { top: `${cardPos.value.top}px`, left: `${cardPos.value.left}px`, width: `${CARD_WIDTH}px` } : {},
)
</script>

<style scoped>
.coach-spotlight {
	position: fixed;
	border-radius: 10px;
	box-shadow: 0 0 0 3px rgb(59 130 246 / 0.9);
	transition:
		top 0.18s ease,
		left 0.18s ease,
		width 0.18s ease,
		height 0.18s ease;
}
.coach-dim {
	box-shadow:
		0 0 0 3px rgb(59 130 246 / 0.9),
		0 0 0 9999px rgb(15 15 15 / 0.35);
}
.coach-card-docked {
	right: 16px;
	bottom: 16px;
	width: min(340px, calc(100vw - 32px));
}
.coach-body :deep(p) {
	margin: 0 0 0.4em;
}
.coach-body :deep(p:last-child) {
	margin-bottom: 0;
}
.coach-body :deep(img) {
	max-width: 100%;
	border-radius: 6px;
	margin: 0.4em 0;
}
</style>
