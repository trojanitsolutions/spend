import type { Directive } from "vue"

/**
 * `v-tour="'bill.supplier'"` or `v-tour="{ key: 'bill.supplier', value: doc.supplier }"`.
 *
 * Marks the element a component renders with `data-tour`, so training steps can
 * point at it, and with `data-tour-value`, so a step can check what was entered
 * even when the control (a Combobox, say) has no plain input to read.
 */
type TourBinding = string | { key: string; value?: unknown }

function apply(el: unknown, binding: TourBinding) {
	if (!(el instanceof HTMLElement)) return // a component with a fragment root has nothing to mark
	const { key, value } = typeof binding === "string" ? { key: binding, value: undefined } : binding
	el.dataset.tour = key
	if (value === undefined) delete el.dataset.tourValue
	else el.dataset.tourValue = value == null ? "" : String(value)
}

export const vTour: Directive<HTMLElement, TourBinding> = {
	mounted: (el, { value }) => apply(el, value),
	updated: (el, { value }) => apply(el, value),
}

/** `[data-tour="key"]` for a tour key, or the selector itself. */
export function targetSelector(target: string, kind: string) {
	return kind === "Selector" ? target : `[data-tour="${CSS.escape(target)}"]`
}

export function findTarget(target: string, kind: string): HTMLElement | null {
	if (!target) return null
	try {
		const matches = document.querySelectorAll<HTMLElement>(targetSelector(target, kind))
		// a list can render the same key more than once; the first visible one is the target
		for (const el of Array.from(matches)) if (el.getClientRects().length) return el
		return matches[0] ?? null
	} catch {
		return null // a hand-edited selector that isn't valid CSS
	}
}

/** What a step's Expected Value is compared with: the tour value, else the control's own value. */
export function readValue(el: HTMLElement): string {
	if (el.dataset.tourValue !== undefined) return el.dataset.tourValue
	const control = el.matches("input, select, textarea")
		? (el as HTMLInputElement)
		: el.querySelector<HTMLInputElement>("input, select, textarea")
	if (control) return control.type === "checkbox" ? String(control.checked) : control.value
	return (el.textContent || "").trim()
}
