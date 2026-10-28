import { reactive } from "vue"
import type { RouteLocationNormalizedLoaded, Router } from "vue-router"
import { toast } from "frappe-ui"
import { getScenarioForEdit, saveScenario, type ActionType, type Step } from "./api"
import { readValue } from "./tour"

const INTERACTIVE = "button, a, input, select, textarea, [role=button], [role=combobox], [role=checkbox], [role=tab], label"
// a tagged element with more controls than this is a container, not the thing clicked
const MAX_CONTROLS_IN_TARGET = 3
const LABEL_LENGTH = 40

export const recorder = reactive({
	scenario: "",
	title: "",
	steps: [] as Step[],
	selected: -1,
	picking: false,
	saving: false,
	dirty: false,
})

/** Open the recorder on a scenario and go to the page it starts on. */
export async function openRecorder(name: string, router: Router) {
	const scenario = await getScenarioForEdit(name)
	Object.assign(recorder, {
		scenario: scenario.name,
		title: scenario.title,
		steps: scenario.steps,
		selected: scenario.steps.length - 1,
		picking: !scenario.steps.length,
		dirty: false,
	})
	const first = scenario.start_route || scenario.steps[0]?.route
	await router.push(first && !first.includes(":") ? first : "/")
}

export function closeRecorder() {
	Object.assign(recorder, { scenario: "", title: "", steps: [], selected: -1, picking: false, dirty: false })
}

export async function saveRecording() {
	recorder.saving = true
	try {
		await saveScenario(recorder.scenario, { steps: recorder.steps })
		recorder.dirty = false
		toast.success("Steps saved")
	} finally {
		recorder.saving = false
	}
}

export function addStep(step: Step) {
	recorder.steps.splice(recorder.selected + 1, 0, step)
	recorder.selected += 1
	recorder.dirty = true
}

export function blankStep(route: RouteLocationNormalizedLoaded, action: ActionType = "Observe"): Step {
	return {
		title: "",
		route: routeOf(route),
		target: "",
		target_kind: "Tour Key",
		target_label: "",
		action_type: action,
		body: "",
		hint: "",
		expected_value: "",
	}
}

/** The step for a click on `node` while picking. */
export function stepFor(node: Element, route: RouteLocationNormalizedLoaded): Step {
	const el = pickElement(node)
	const tagged = el.closest<HTMLElement>("[data-tour]")
	const action = guessAction(el)
	const label = describe(el)
	const step = blankStep(route, action)
	step.title = `${action === "Click" ? "Click" : action === "Observe" ? "Look at" : "Fill in"} ${label}`
	step.target_label = label
	if (tagged) {
		step.target = tagged.dataset.tour!
		if (action !== "Click") step.expected_value = readValue(tagged)
	} else {
		step.target = buildSelector(el)
		step.target_kind = "Selector"
	}
	return step
}

/** The element a click means: a tagged control when there is one, else the nearest control. */
export function pickElement(node: Element): HTMLElement {
	const tagged = node.closest<HTMLElement>("[data-tour]")
	if (tagged && tagged.querySelectorAll(INTERACTIVE).length <= MAX_CONTROLS_IN_TARGET) return tagged
	return (node.closest<HTMLElement>(INTERACTIVE) || node) as HTMLElement
}

/** Path for a step: the route pattern on a page with params (`/bills/:name`), else the path. */
export function routeOf(route: RouteLocationNormalizedLoaded) {
	const pattern = route.matched.at(-1)?.path
	return Object.keys(route.params).length && pattern ? pattern : route.path
}

function guessAction(el: HTMLElement): ActionType {
	const control = el.matches("input, select, textarea, [role=combobox]")
		? el
		: el.querySelector<HTMLElement>("input, select, textarea, [role=combobox]")
	if (!control) return el.matches(INTERACTIVE) || el.querySelector(INTERACTIVE) ? "Click" : "Observe"
	if (control.matches("select, [role=combobox]")) return "Select Option"
	if (control.matches("input[type=checkbox], input[type=radio]")) return "Click"
	return "Enter Value"
}

function describe(el: HTMLElement): string {
	const text =
		el.getAttribute("aria-label") ||
		el.querySelector("label")?.textContent ||
		el.closest("label")?.textContent ||
		el.getAttribute("placeholder") ||
		el.querySelector("[placeholder]")?.getAttribute("placeholder") ||
		el.textContent ||
		el.tagName.toLowerCase()
	const clean = text.replace(/\s+/g, " ").replace(/\*$/, "").trim()
	return clean.length > LABEL_LENGTH ? `${clean.slice(0, LABEL_LENGTH)}…` : clean
}

/**
 * A CSS selector for an untagged element: the shortest chain of tag, aria-label
 * and position that matches only it. It breaks when the markup changes, which is
 * why the recorder flags these steps as fragile.
 */
export function buildSelector(el: Element): string {
	const parts: string[] = []
	let node: Element | null = el
	while (node && node !== document.body) {
		if (node.id && isStableId(node.id)) {
			parts.unshift(`#${CSS.escape(node.id)}`)
			break
		}
		parts.unshift(segment(node))
		const selector = parts.join(" > ")
		if (document.querySelectorAll(selector).length === 1) return selector
		node = node.parentElement
	}
	return parts.join(" > ")
}

function segment(node: Element) {
	const tag = node.tagName.toLowerCase()
	const label = node.getAttribute("aria-label")
	if (label) return `${tag}[aria-label="${label.replace(/["\\]/g, "\\$&")}"]`
	const siblings = node.parentElement ? Array.from(node.parentElement.children).filter((c) => c.tagName === node.tagName) : []
	return siblings.length > 1 ? `${tag}:nth-of-type(${siblings.indexOf(node) + 1})` : tag
}

// generated ids (reka-123, v-0-1) change between renders
function isStableId(id: string) {
	return !/\d/.test(id) && !/^(reka|radix|headlessui|v-)/.test(id)
}
