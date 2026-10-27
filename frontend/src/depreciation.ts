// Client-side mirror of spend/spend/depreciation.py, used only for the live preview
// on the new-asset form. The server recomputes the schedule on save.

const FREQUENCY_MONTHS: Record<string, number> = { Monthly: 1, Quarterly: 3, "Half-Yearly": 6, Yearly: 12 }

export interface PreviewInput {
	cost: number
	salvage: number
	method: string
	frequency: string
	usefulLifeYears: number
	availableForUseDate: string
	startDate?: string
	annualRate?: number
}

const round = (v: number) => Math.round(v * 100) / 100
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
const lastDay = (y: number, m: number) => new Date(y, m + 1, 0)

function addMonths(value: string, months: number, monthEnd: boolean): string {
	const [y, m, d] = value.split("-").map(Number)
	const target = lastDay(y, m - 1 + months)
	return iso(monthEnd ? target : new Date(target.getFullYear(), target.getMonth(), Math.min(d, target.getDate())))
}

export function previewSchedule(input: PreviewInput) {
	const step = FREQUENCY_MONTHS[input.frequency]
	const periods = (input.usefulLifeYears * 12) / step
	if (!input.cost || !input.availableForUseDate || !input.usefulLifeYears) return { rows: [], error: "" }
	if (input.salvage < 0 || input.salvage >= input.cost)
		return { rows: [], error: "Salvage value must be less than the purchase amount." }
	if (periods < 1 || Math.abs(periods - Math.round(periods)) > 1e-6)
		return { rows: [], error: `Useful life must be a whole number of ${input.frequency.toLowerCase()} periods.` }

	const n = Math.round(periods)
	let rate = 1 / n
	if (input.method === "Written Down Value") {
		if (input.annualRate) rate = 1 - (1 - input.annualRate / 100) ** (step / 12)
		else if (input.salvage > 0) rate = 1 - (input.salvage / input.cost) ** (1 / n)
		else return { rows: [], error: "Written Down Value needs an annual rate or a salvage value above zero." }
	}

	const [y, m] = input.availableForUseDate.split("-").map(Number)
	const start = input.startDate || iso(lastDay(y, m - 1 + step - 1))
	const [sy, sm, sd] = start.split("-").map(Number)
	const monthEnd = lastDay(sy, sm - 1).getDate() === sd

	const rows: { date: string; amount: number; closing: number }[] = []
	let book = input.cost
	const straight = round((input.cost - input.salvage) / n)
	for (let i = 0; i < n; i++) {
		const depreciable = round(book - input.salvage)
		if (depreciable <= 0) break
		let amount = i === n - 1 ? depreciable : input.method === "Straight Line" ? straight : round(book * rate)
		amount = round(Math.min(Math.max(amount, 0), depreciable))
		if (amount <= 0) continue
		book = round(book - amount)
		rows.push({ date: addMonths(start, i * step, monthEnd), amount, closing: book })
	}
	return { rows, error: "" }
}
