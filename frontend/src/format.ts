const formatters = new Map<string, Intl.NumberFormat>()

export function money(value: number | null | undefined, currency = "", compact = false): string {
	const key = `${currency}|${compact}`
	if (!formatters.has(key)) {
		const options: Intl.NumberFormatOptions = compact
			? { notation: "compact", maximumFractionDigits: 1 }
			: { minimumFractionDigits: 2, maximumFractionDigits: 2 }
		if (currency) Object.assign(options, { style: "currency", currency })
		try {
			formatters.set(key, new Intl.NumberFormat(undefined, options))
		} catch {
			formatters.set(key, new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }))
		}
	}
	return formatters.get(key)!.format(Number(value || 0))
}

export function percent(value: number | null | undefined, digits = 1): string {
	return `${Number(value || 0).toFixed(digits)}%`
}

export function date(value: string | null | undefined): string {
	if (!value) return ""
	const d = new Date(`${value}T00:00:00`)
	return Number.isNaN(d.getTime())
		? value
		: d.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" })
}

export function today(): string {
	const d = new Date()
	const pad = (n: number) => String(n).padStart(2, "0")
	return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function addDays(value: string, days: number): string {
	const d = new Date(`${value}T00:00:00`)
	d.setDate(d.getDate() + days)
	const pad = (n: number) => String(n).padStart(2, "0")
	return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** Tone for a utilization percentage: on track, near the limit, or over it. */
export function utilizationTone(value: number): "green" | "amber" | "red" {
	if (value > 100) return "red"
	if (value >= 80) return "amber"
	return "green"
}

export const ASSET_STATUS_THEME: Record<string, "gray" | "blue" | "green" | "amber" | "red" | "violet"> = {
	Draft: "red",
	Submitted: "blue",
	"Partially Depreciated": "amber",
	"Fully Depreciated": "green",
	Cancelled: "gray",
}

export function docstatusLabel(docstatus: number) {
	return ["Draft", "Submitted", "Cancelled"][docstatus] || ""
}

/** Status of a document that may be under approval: its approval stage while it is a draft. */
export function approvalLabel(docstatus: number, workflowState?: string | null, status?: string) {
	if (docstatus === 0 && workflowState && workflowState !== "Draft") return workflowState
	return status || docstatusLabel(docstatus)
}

/** Expenses and recurring payment postings live under /expenses; other entries under /journals. */
export const EXPENSE_TYPES = ["Expense Entry", "Recurring Payment"]

export function entryPath(name: string, voucherType: string) {
	return `${EXPENSE_TYPES.includes(voucherType) ? "/expenses" : "/journals"}/${name}`
}
