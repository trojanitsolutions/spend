import { call, toast } from "frappe-ui"

export type Row = Record<string, any>

export interface ReportColumn {
	fieldname: string
	label: string
	fieldtype?: string
	options?: string
	width?: number
	hidden?: number
}

export interface ReportResult {
	columns: ReportColumn[]
	result: Row[]
	chart?: any
	report_summary?: { label: string; value: number; datatype?: string; indicator?: string }[]
}

export function errorMessage(error: any): string {
	const messages = error?.messages || error?.exc?.messages
	if (Array.isArray(messages) && messages.length) return messages.join("\n").replace(/<[^>]+>/g, "")
	return (error?.message || String(error)).replace(/<[^>]+>/g, "")
}

/** Call a whitelisted method; shows server errors as a toast and rethrows. */
export async function api<T = any>(method: string, args: Row = {}, { silent = false } = {}): Promise<T> {
	try {
		return await call<T>(method, args)
	} catch (error) {
		if (!silent) toast.error(errorMessage(error))
		throw error
	}
}

export function getList<T = Row>(
	doctype: string,
	fields: string[],
	filters: Row | any[] = {},
	orderBy = "creation desc",
	limit = 100,
): Promise<T[]> {
	return api<T[]>("frappe.client.get_list", {
		doctype,
		fields,
		filters,
		order_by: orderBy,
		limit_page_length: limit,
	}).then((rows) => {
		// a filter on a child table repeats a document once per matching row
		const seen = new Set()
		return rows.filter((r: any) => r.name === undefined || (!seen.has(r.name) && seen.add(r.name)))
	})
}

export function getDoc<T = Row>(doctype: string, name: string): Promise<T> {
	return api<T>("frappe.client.get", { doctype, name })
}

export function insertDoc<T = Row>(doc: Row): Promise<T> {
	return api<T>("frappe.client.insert", { doc })
}

export function submitDoc(doctype: string, name: string) {
	return api("spend.api.submit_doc", { doctype, name })
}

export function cancelDoc(doctype: string, name: string) {
	return api("spend.api.cancel_doc", { doctype, name })
}

export const APPROVAL = {
	send: "Send for Approval",
	approve: "Approve",
	reject: "Reject",
	resubmit: "Resubmit",
	revise: "Revise",
}

export function applyAction(doctype: string, name: string, action: string, reason?: string) {
	return api<{ name: string; workflow_state: string; docstatus: number }>("spend.spend.approval.apply_action", {
		doctype,
		name,
		action,
		reason,
	})
}

export interface Version {
	name: string
	docstatus: number
	workflow_state?: string
	status?: string
	total: number
	net_change: number | null
	reason?: string
	owner_name: string
	changes?: { account: string; before: number; after: number; change: number }[]
}

export function getAmendment<T = Row>(doctype: string, name: string) {
	return api<{ existing?: string; doc?: T; previous?: Row }>("spend.spend.amendment.get_amendment", { doctype, name })
}

export function getVersions(doctype: string, name: string) {
	return api<Version[]>("spend.spend.amendment.get_versions", { doctype, name })
}

export interface BudgetAllocation {
	name: string
	company: string
	cost_center: string
	cost_center_is_group: 0 | 1
	lft: number
	rgt: number
	action_if_exceeded: string
	currency: string
	total: number
	held: number
	free: number
	accounts: { account: string; budget: number; held: number; free: number }[]
	projects: { name: string; project_name: string; budget_amount: number; status: string; accounts: Record<string, number>; spent: number; route: string }[]
	// every recurring payment on the budget; those of a project (counted false) take from its share
	recurring: { name: string; title: string; project: string | null; project_name: string | null; counted: boolean; account: string; budget_amount: number; paid: number; remaining: number; status: string; route: string }[]
	recurring_held: number
	recurring_paid: number
	recurring_remaining: number
}

export function getBudgetAllocation(budget: string, project?: string) {
	return api<BudgetAllocation>("spend.spend.doctype.project.project.get_budget_allocation", { budget, project })
}

// what a recurring payment can take: the Budget's free amounts, or what is left of the project's share
export interface RecurringRoom {
	budget: string
	project: string | null
	// false when the project has no share: the payment then takes from the Budget
	share: boolean
	fiscal_year: string
	year_start: string
	year_end: string
	cost_center: string
	cost_center_is_group: 0 | 1
	lft: number
	rgt: number
	default_cost_center: string | null
	currency: string
	accounts: { account: string; limit: number | null; held: number; free: number | null }[]
	total: number | null
	held: number
	free: number | null
}

export function getRecurringRoom(budget?: string, project?: string, silent = false) {
	return api<RecurringRoom | null>("spend.spend.doctype.recurring_payment.recurring_payment.get_recurring_room", { budget, project }, { silent })
}

export function runReport(reportName: string, filters: Row): Promise<ReportResult> {
	const clean = Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== "" && v != null))
	return api<ReportResult>("frappe.desk.query_report.run", {
		report_name: reportName,
		filters: clean,
		ignore_prepared_report: true,
	})
}

/** `query` is a whitelisted search method that replaces the standard one. */
export function searchLink(doctype: string, txt: string, filters: Row = {}, query?: string) {
	return api<{ value: string; description?: string; label?: string }[]>(
		"frappe.desk.search.search_link",
		{ doctype, txt, filters, query, page_length: 20 },
		{ silent: true },
	)
}

// parent categories, or the sub categories of `parent_category`; limited to a project's categories when it has any
export const CATEGORY_QUERY = "spend.spend.doctype.expense_category.expense_category.get_categories"

export function getCategoryAccount(category?: string, subCategory?: string) {
	return api<string | null>("spend.spend.expense_category.get_category_account", { category, sub_category: subCategory }, { silent: true }).catch(() => null)
}

/** "Materials - N / Cement - N" for a category and its sub category. */
export function categoryLabel(category?: string | null, subCategory?: string | null) {
	return [category, subCategory].filter(Boolean).join(" / ")
}
