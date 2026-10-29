import { computed, reactive } from "vue"
import { dialog } from "frappe-ui"
import { api, applyAction, APPROVAL, submitDoc } from "./api"
import { applyTheme } from "./theme"

interface Company {
	name: string
	abbr: string
	default_currency: string
	is_training: 0 | 1
	has_demo_data: boolean
}

interface FiscalYear {
	name: string
	start_date: string
	end_date: string
}

type Perms = Record<string, { read: boolean; create: boolean; submit: boolean; write: boolean; delete: boolean; cancel: boolean }>

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
	reports: [] as string[],
	unread: 0,
	company: "" as string,
	canSetup: false,
	isTrainer: false,
	defaultCurrency: "",
})

export const inTrainingCompany = computed(
	() => !!session.companies.find((c) => c.name === session.company)?.is_training,
)

/** The current company holds demo data that can be cleared in Settings. */
export const hasDemoData = computed(() => !!session.companies.find((c) => c.name === session.company)?.has_demo_data)

export const currency = computed(
	() => session.companies.find((c) => c.name === session.company)?.default_currency || "",
)

export function can(doctype: string, action: "read" | "create" | "submit" | "write" | "delete" | "cancel") {
	return Boolean(session.permissions[doctype]?.[action])
}

/** Whether the user may open this doctype: read permission and its module not blocked for them. */
export function canRead(doctype: string) {
	return can(doctype, "read")
}

/** Whether the user may run this report: one of their roles is allowed and its module is not blocked. */
export function canRunReport(name: string) {
	return session.reports.includes(name)
}

/** Whether documents of this type go through General Manager approval before posting. */
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

/** Desk is for System Managers; the server sends everyone else back to /spend. */
export const deskAccess = computed(() => hasRole("System Manager"))

export function setCompany(name: string) {
	session.company = name
	try {
		localStorage.setItem(STORAGE_KEY, name)
	} catch {
		// storage can be unavailable (private mode); the choice just won't persist
	}
}

/** Ask first, then end the session and go to the login page. */
export function logout() {
	dialog.confirm({
		title: "Log out of Spend?",
		message: "You will need to sign in again to continue.",
		confirmLabel: "Log out",
		onConfirm: async () => {
			try {
				await api("logout", {}, { silent: true })
			} finally {
				window.location.href = "/login"
			}
		},
	})
}

let loading: Promise<void> | undefined

/** Load the boot data once; later calls wait for the same load. */
export function loadSession() {
	loading ||= fetchSession()
	return loading
}

/** Load the boot data again, e.g. after the first company is created. */
export function reloadSession() {
	loading = fetchSession()
	return loading
}

async function fetchSession() {
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
			reports: boot.reports,
			canSetup: boot.can_setup,
			isTrainer: boot.is_trainer,
			defaultCurrency: boot.default_currency,
		})
		applyTheme(boot.theme)
		const names = boot.companies.map((c: Company) => c.name)
		const stored = readStoredCompany()
		// the training company is only opened on purpose, never as the fallback
		const firstReal = boot.companies.find((c: Company) => !c.is_training)?.name
		session.company = [stored, boot.default_company, firstReal, names[0]].find((c) => c && names.includes(c)) || ""
	} catch (error: any) {
		session.error = error?.status === 403 || /permission/i.test(String(error)) ? "forbidden" : "failed"
	} finally {
		session.ready = true
	}
}
