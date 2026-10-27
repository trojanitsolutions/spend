import { reactive, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

type Row = Record<string, any>

export interface FilterField {
	/** key in the filter values; a date range uses `<key>_from` and `<key>_to` */
	key: string
	label: string
	type: "date-range" | "select" | "link"
	doctype?: string
	options?: string[]
	/** link search filters */
	filters?: Row
	/** column filtered on, `key` by default */
	field?: string
	/** child table the column is on, for server filters */
	child?: string
	/** server filters for a value, when it is not `field = value` */
	server?: (value: string) => any[][]
	/** client match for a value, when it is not `row[field] === value` */
	match?: (row: Row, value: string) => boolean
}

export function valueKeys(field: FilterField) {
	return field.type === "date-range" ? [`${field.key}_from`, `${field.key}_to`] : [field.key]
}

/** Filter values kept in the URL query, so they survive going back to the list. */
export function useListFilters(fields: FilterField[]) {
	const route = useRoute()
	const router = useRouter()
	const keys = fields.flatMap(valueKeys)
	const values = reactive<Record<string, string>>(Object.fromEntries(keys.map((k) => [k, (route.query[k] as string) || ""])))

	watch(values, () => {
		const query: Row = { ...route.query }
		for (const k of keys) {
			if (values[k]) query[k] = values[k]
			else delete query[k]
		}
		router.replace({ query })
	})
	return values
}

/** `frappe.client.get_list` filters for the values, after the `base` ones. */
export function toServerFilters(doctype: string, fields: FilterField[], values: Row, base: Row = {}) {
	const out: any[][] = Object.entries(base).map(([k, v]) => [doctype, k, ...(Array.isArray(v) ? v : ["=", v])])
	for (const f of fields) {
		const column = f.field || f.key
		const dt = f.child || doctype
		if (f.type === "date-range") {
			const [from, to] = valueKeys(f).map((k) => values[k])
			if (from) out.push([dt, column, ">=", from])
			if (to) out.push([dt, column, "<=", to])
			continue
		}
		const value = values[f.key]
		if (!value) continue
		out.push(...(f.server ? f.server(value) : [[dt, column, "=", value]]))
	}
	return out
}

/** For lists loaded whole: whether `row` passes the filters. */
export function matchRow(fields: FilterField[], values: Row, row: Row) {
	return fields.every((f) => {
		const column = f.field || f.key
		if (f.type === "date-range") {
			const [from, to] = valueKeys(f).map((k) => values[k])
			if (f.match) return f.match(row, `${from || ""}|${to || ""}`)
			const v = row[column]
			return (!from || (v && v >= from)) && (!to || (v && v <= to))
		}
		const value = values[f.key]
		if (!value) return true
		return f.match ? f.match(row, value) : row[column] === value
	})
}

const DOCSTATUS: Record<string, number> = { Draft: 0, Submitted: 1, Cancelled: 2 }

/** A Draft / Submitted / Cancelled filter on `docstatus`. */
export const docstatusFilter: FilterField = {
	key: "docstatus",
	label: "Status",
	type: "select",
	options: Object.keys(DOCSTATUS),
	server: (v) => [["docstatus", "=", DOCSTATUS[v]]],
	match: (row, v) => row.docstatus === DOCSTATUS[v],
}

/** Client match for a date range: the row's own `start`–`end` period overlaps it. */
export function overlaps(start: string, end: string) {
	return (row: Row, range: string) => {
		const [from, to] = range.split("|")
		return (!from || !row[end] || row[end] >= from) && (!to || !row[start] || row[start] <= to)
	}
}
