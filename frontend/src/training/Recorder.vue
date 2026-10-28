<template>
	<div v-if="recorder.picking && hover" class="recorder-hover pointer-events-none fixed z-[70]" :style="hoverStyle" />
	<div
		data-training-ui
		class="fixed bottom-4 left-4 z-[70] flex max-h-[calc(100vh-2rem)] w-[min(380px,calc(100vw-2rem))] flex-col rounded-xl border border-outline-gray-2 bg-surface-base text-ink-gray-8 shadow-2xl"
	>
		<div class="flex items-center gap-2 border-b border-outline-gray-1 px-3 py-2">
			<span class="size-2 shrink-0 rounded-full" :class="recorder.picking ? 'animate-pulse bg-red-500' : 'bg-surface-gray-5'" aria-hidden="true" />
			<div class="min-w-0 flex-1">
				<div class="truncate text-sm font-semibold">{{ recorder.title }}</div>
				<div class="text-xs text-ink-gray-5">{{ recorder.picking ? "Click an element on the page · Esc to stop" : `${recorder.steps.length} steps` }}</div>
			</div>
			<Button size="sm" variant="ghost" :icon="collapsed ? 'lucide-chevron-up' : 'lucide-chevron-down'" :aria-label="collapsed ? 'Expand' : 'Collapse'" @click="collapsed = !collapsed" />
			<Button size="sm" variant="ghost" icon="lucide-x" aria-label="Close recorder" @click="close" />
		</div>

		<template v-if="!collapsed">
			<div class="flex flex-wrap gap-1.5 border-b border-outline-gray-1 px-3 py-2">
				<Button size="sm" :variant="recorder.picking ? 'solid' : 'subtle'" icon-left="lucide-mouse-pointer-click" :label="recorder.picking ? 'Picking…' : 'Pick element'" @click="recorder.picking = !recorder.picking" />
				<Button size="sm" icon-left="lucide-eye" label="Add note" title="A step with no element: read and press Next" @click="addStep(blankStep(route))" />
			</div>

			<ol class="max-h-48 shrink-0 overflow-y-auto py-1">
				<li v-for="(s, i) in recorder.steps" :key="i">
					<div
						role="button"
						tabindex="0"
						class="group flex cursor-pointer items-center gap-2 px-3 py-1 text-sm"
						:class="i === recorder.selected ? 'bg-surface-gray-2' : 'hover:bg-surface-gray-1'"
						@click="recorder.selected = i"
						@keydown.enter="recorder.selected = i"
					>
						<span class="w-5 shrink-0 text-right tabular-nums text-ink-gray-5">{{ i + 1 }}</span>
						<span class="min-w-0 flex-1 truncate">{{ s.title || "Untitled step" }}</span>
						<span v-if="s.target_kind === 'Selector'" class="lucide-triangle-alert size-3.5 shrink-0 text-ink-amber-3" title="Fragile target" aria-label="Fragile target" />
						<span class="hidden shrink-0 gap-0.5 group-hover:flex">
							<button type="button" class="rounded p-0.5 hover:bg-surface-gray-3" aria-label="Move up" :disabled="i === 0" @click.stop="move(i, -1)"><span class="lucide-arrow-up size-3.5" aria-hidden="true" /></button>
							<button type="button" class="rounded p-0.5 hover:bg-surface-gray-3" aria-label="Move down" :disabled="i === recorder.steps.length - 1" @click.stop="move(i, 1)"><span class="lucide-arrow-down size-3.5" aria-hidden="true" /></button>
							<button type="button" class="rounded p-0.5 hover:bg-surface-gray-3" aria-label="Delete step" @click.stop="remove(i)"><span class="lucide-trash-2 size-3.5" aria-hidden="true" /></button>
						</span>
					</div>
				</li>
				<li v-if="!recorder.steps.length" class="px-3 py-3 text-sm text-ink-gray-5">Pick the first element the trainee should use.</li>
			</ol>

			<div v-if="selectedStep" class="min-h-0 flex-1 overflow-y-auto border-t border-outline-gray-1 px-3 py-3">
				<StepFields v-model="recorder.steps[recorder.selected]" :scenario="recorder.scenario" @change="recorder.dirty = true" />
				<Button v-if="recorder.picking === false" class="mt-2" size="sm" variant="ghost" icon-left="lucide-crosshair" label="Pick again for this step" @click="repick = true; recorder.picking = true" />
			</div>

			<div class="flex items-center justify-end gap-2 border-t border-outline-gray-1 px-3 py-2">
				<span v-if="recorder.dirty" class="mr-auto text-xs text-ink-amber-3">Unsaved changes</span>
				<Button size="sm" icon-left="lucide-play" label="Try it" :disabled="!recorder.steps.length" @click="tryIt" />
				<Button size="sm" variant="solid" label="Save" :loading="recorder.saving" :disabled="!recorder.dirty" @click="saveRecording" />
			</div>
		</template>
	</div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { Button, dialog } from "frappe-ui"
import { addStep, blankStep, closeRecorder, pickElement, recorder, saveRecording, stepFor } from "./recorder"
import { isTrainingUi, startRun } from "./run"
import StepFields from "./StepFields.vue"

const route = useRoute()
const router = useRouter()
const collapsed = ref(false)
const hover = ref<DOMRect | null>(null)
// picking for the selected step instead of adding a new one
const repick = ref(false)

const selectedStep = computed(() => recorder.steps[recorder.selected])
const hoverStyle = computed(() => {
	const r = hover.value
	return r ? { top: `${r.top - 3}px`, left: `${r.left - 3}px`, width: `${r.width + 6}px`, height: `${r.height + 6}px` } : {}
})

watch(
	() => recorder.picking,
	(picking) => {
		if (!picking) {
			hover.value = null
			repick.value = false
		}
	},
)

function onMove(event: MouseEvent) {
	if (!recorder.picking) return
	const node = event.target as Element
	hover.value = isTrainingUi(node) ? null : pickElement(node).getBoundingClientRect()
}

// while picking, the page must not react: no navigation, no dialogs, no focus
function block(event: Event) {
	if (!recorder.picking || isTrainingUi(event.target)) return
	event.preventDefault()
	event.stopPropagation()
	event.stopImmediatePropagation()
	if (event.type !== "click") return
	const step = stepFor(event.target as Element, route)
	if (repick.value && selectedStep.value) {
		Object.assign(selectedStep.value, {
			target: step.target,
			target_kind: step.target_kind,
			target_label: step.target_label,
			route: step.route,
		})
		recorder.dirty = true
	} else {
		addStep(step)
	}
	recorder.picking = false
}

function onKey(event: KeyboardEvent) {
	if (event.key === "Escape" && recorder.picking) recorder.picking = false
}

const BLOCKED = ["pointerdown", "mousedown", "mouseup", "click", "focusin"] as const
onMounted(() => {
	document.addEventListener("mousemove", onMove, true)
	document.addEventListener("keydown", onKey, true)
	for (const type of BLOCKED) document.addEventListener(type, block, true)
})
onBeforeUnmount(() => {
	document.removeEventListener("mousemove", onMove, true)
	document.removeEventListener("keydown", onKey, true)
	for (const type of BLOCKED) document.removeEventListener(type, block, true)
})

function move(i: number, delta: number) {
	const [s] = recorder.steps.splice(i, 1)
	recorder.steps.splice(i + delta, 0, s)
	recorder.selected = i + delta
	recorder.dirty = true
}

function remove(i: number) {
	recorder.steps.splice(i, 1)
	recorder.selected = Math.min(recorder.selected, recorder.steps.length - 1)
	recorder.dirty = true
}

function close() {
	if (!recorder.dirty) return closeRecorder()
	dialog.confirm({
		title: "Close without saving?",
		message: "The steps you changed since the last save will be lost.",
		confirmLabel: "Close",
		onConfirm: closeRecorder,
	})
}

/** Save, then play the scenario in Guided mode. */
async function tryIt() {
	if (recorder.dirty) await saveRecording()
	const name = recorder.scenario
	closeRecorder()
	await startRun(name, "Guided", router)
}
</script>

<style scoped>
.recorder-hover {
	border-radius: 6px;
	outline: 2px dashed rgb(239 68 68 / 0.9);
	background: rgb(239 68 68 / 0.08);
}
</style>
