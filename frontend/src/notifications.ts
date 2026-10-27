import { reactive } from "vue"
import { api } from "./api"
import { session } from "./store"

export interface SpendNotification {
	name: string
	subject: string
	email_content?: string
	type: string
	document_type?: string
	document_name?: string
	link?: string
	read: 0 | 1
	creation: string
}

export const counts = reactive({ unread: 0, pending: 0 })

export async function refreshCounts() {
	try {
		Object.assign(counts, await api("spend.spend.notifications.get_counts", { company: session.company }, { silent: true }))
	} catch {
		// counts are a convenience; a failed poll keeps the last values
	}
}

export function getNotifications(limit = 20, unreadOnly = false) {
	return api<SpendNotification[]>("spend.spend.notifications.get_notifications", { limit, unread_only: unreadOnly ? 1 : 0 })
}

export async function markRead(names?: string[]) {
	await api("spend.spend.notifications.mark_read", names ? { names } : {})
	await refreshCounts()
}

/** Where a notification leads: an app route (starting with "/"), or a Desk URL to open in a new tab. */
export function notificationTarget(n: SpendNotification): { route?: string; href?: string } {
	if (n.link?.startsWith("/spend/")) return { route: n.link.slice("/spend".length) }
	if (n.link) return { href: n.link }
	if (n.document_type && n.document_name) {
		const slug = n.document_type.toLowerCase().replace(/ /g, "-")
		return { href: `/app/${slug}/${encodeURIComponent(n.document_name)}` }
	}
	return {}
}

export const TYPE_ICONS: Record<string, string> = {
	Approval: "lucide-shield-check",
	"Budget Alert": "lucide-triangle-alert",
	"Bill Reminder": "lucide-calendar-clock",
	"Recurring Payment": "lucide-repeat",
}

export function timeAgo(value: string) {
	const minutes = Math.floor((Date.now() - Date.parse(value.replace(" ", "T"))) / 60000)
	if (minutes < 1) return "just now"
	if (minutes < 60) return `${minutes} min ago`
	const hours = Math.floor(minutes / 60)
	if (hours < 24) return `${hours} h ago`
	return `${Math.floor(hours / 24)} d ago`
}
