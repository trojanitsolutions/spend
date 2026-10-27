import { computed, reactive } from "vue"
import { api, applyAction, APPROVAL, submitDoc } from "./api"

interface Company {
	name: string
	abbr: string
	default_currency: string
}

interface FiscalYear {
	name: string
	start_date: string
	end_date: string
}

type Perms = Record<string, { create: boolean; submit: boolean; write: boolean; delete: boolean; cancel: boolean }>

const STORAGE_KEY = "spend:company"

function readStoredCompany(): string | null {
	try {
		return localStorage.getItem(STORAGE_KEY)
	} catch {
		return null
	}
}

export const session = reactive({
	ready: false,
	error: "",
	user: "",
	fullName: "",
	companies: [] as Company[],
	fiscalYears: [] as FiscalYear[],
	currentFiscalYear: null as string | null,
	permissions: {} as Perms,
	approvals: [] as string[],
	roles: [] as string[],
	unread: 0,
	company: "" as string,
})

export const currency = computed(
	() => session.companies.find((c) => c.name === session.company)?.default_currency || "",
)

export function can(doctype: string, action: "create" | "submit" | "write" | "delete" | "cancel") {
	return Boolean(session.permissions[doctype]?.[action])
}

/** Whether documents of this type go through Accounts Manager and GM approval before posting. */
export function needsApproval(doctype: string) {
	return session.approvals.includes(doctype)
}

/** Submit the document, or send it for approval when its type needs approval. True when sent. */
export async function submitOrSend(doctype: string, name: string): Promise<boolean> {
	if (needsApproval(doctype)) {
		await applyAction(doctype, name, APPROVAL.send)
		return true
	}
	await submitDoc(doctype, name)
	return false
}

export function hasRole(role: string) {
	return session.roles.includes(role)
}

export function setCompany(name: string) {
	session.company = name
	try {
		localStorage.setItem(STORAGE_KEY, name)
	} catch {
		// storage can be unavailable (private mode); the choice just won't persist
	}
}

export async function loadSession() {
	try {
		const boot = await api("spend.api.get_boot", {}, { silent: true })
		Object.assign(session, {
			user: boot.user,
			fullName: boot.full_name,
			companies: boot.companies,
			fiscalYears: boot.fiscal_years,
			currentFiscalYear: boot.current_fiscal_year,
			permissions: boot.permissions,
			approvals: boot.approvals,
			roles: boot.roles,
		})
		const names = boot.companies.map((c: Company) => c.name)
		const stored = readStoredCompany()
		session.company = [stored, boot.default_company, names[0]].find((c) => c && names.includes(c)) || ""
	} catch (error: any) {
		session.error = error?.status === 403 || /permission/i.test(String(error)) ? "forbidden" : "failed"
	} finally {
		session.ready = true
	}
}
