<template>
	<div class="flex h-screen bg-surface-base text-ink-gray-8">
		<!-- sidebar -->
		<aside
			:class="[
				'fixed inset-y-0 left-0 z-30 flex w-60 flex-col border-r border-outline-gray-1 bg-surface-gray-1 transition-transform md:static md:translate-x-0',
				menuOpen ? 'translate-x-0' : '-translate-x-full',
			]"
		>
			<div class="flex items-center gap-2 px-4 pb-3 pt-4">
				<img v-if="appLogo" :src="appLogo" alt="" class="size-7 shrink-0 rounded-lg object-contain" @error="appLogo = ''" />
				<div v-else class="flex size-7 items-center justify-center rounded-lg bg-surface-gray-9">
					<span class="lucide-wallet size-4 text-white" aria-hidden="true" />
				</div>
				<div class="min-w-0 flex-1">
					<div class="text-base font-semibold leading-tight text-ink-gray-9">Spend</div>
					<div class="truncate text-xs text-ink-gray-5">{{ session.fullName }}</div>
				</div>
				<NotificationBell class="hidden md:block" />
			</div>

			<div class="px-3 pb-2">
				<label class="sr-only" for="company-switcher">Company</label>
				<select
					id="company-switcher"
					v-tour="'shell.company'"
					class="form-select w-full text-sm"
					:value="session.company"
					@change="switchCompany(($event.target as HTMLSelectElement).value)"
				>
					<option v-for="c in session.companies" :key="c.name" :value="c.name">{{ c.name }}</option>
				</select>
			</div>

			<nav class="flex-1 overflow-y-auto px-2 pb-4">
				<template v-for="group in visibleNav" :key="group.label">
					<div v-if="group.label" class="px-2 pb-1 pt-4 text-xs font-medium uppercase tracking-wide text-ink-gray-4">
						{{ group.label }}
					</div>
					<RouterLink
						v-for="item in group.items"
						:key="item.to"
						v-tour="navKey(item.to)"
						:to="item.to"
						class="flex items-center gap-2.5 rounded-md px-2 py-1.5 text-base text-ink-gray-7 transition-colors hover:bg-surface-gray-2"
						:class="{ 'bg-surface-base font-medium text-ink-gray-9 shadow-sm hover:bg-surface-base': isActive(item.to) }"
						@click="menuOpen = false"
					>
						<span :class="[item.icon, 'size-4 shrink-0 text-ink-gray-6']" aria-hidden="true" />
						<span class="flex-1">{{ item.label }}</span>
						<span v-if="badges[item.to]" class="rounded-full bg-surface-amber-2 px-1.5 text-xs font-medium tabular-nums text-ink-amber-4">{{ badges[item.to] }}</span>
					</RouterLink>
				</template>
			</nav>

			<div class="space-y-0.5 border-t border-outline-gray-1 p-3">
				<a v-if="deskAccess" href="/app/spend" class="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-ink-gray-6 hover:bg-surface-gray-2">
					<span class="lucide-layout-grid size-4" aria-hidden="true" /> Open Desk
				</a>
				<button
					type="button"
					class="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm text-ink-gray-6 hover:bg-surface-gray-2"
					@click="logout"
				>
					<span class="lucide-log-out size-4" aria-hidden="true" /> Log out
				</button>
			</div>
		</aside>
		<div v-if="menuOpen" class="fixed inset-0 z-20 bg-black/30 md:hidden" @click="menuOpen = false" />

		<!-- content -->
		<div class="flex min-w-0 flex-1 flex-col">
			<header class="flex items-center gap-3 border-b border-outline-gray-1 px-4 py-2.5 md:hidden">
				<Button variant="ghost" icon="lucide-menu" aria-label="Open menu" @click="menuOpen = true" />
				<img v-if="appLogo" :src="appLogo" alt="" class="size-6 shrink-0 rounded-md object-contain" @error="appLogo = ''" />
				<span class="flex-1 font-semibold">Spend</span>
				<NotificationBell />
			</header>
			<div v-if="inTrainingCompany" class="flex flex-wrap items-center gap-2 border-b border-outline-amber-2 bg-surface-amber-1 px-4 py-1.5 text-sm text-ink-amber-4 sm:px-6">
				<span class="lucide-graduation-cap size-4" aria-hidden="true" />
				<span class="flex-1">Training company: entries here are for practice and never reach your books.</span>
				<button v-if="!state.run" type="button" class="font-medium underline" @click="leaveTraining">Leave</button>
			</div>
			<main class="min-w-0 flex-1 overflow-y-auto">
				<slot />
			</main>
		</div>
		<TrainingLayer />
	</div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useRoute } from "vue-router"
import { Button } from "frappe-ui"
import NotificationBell from "@/components/NotificationBell.vue"
import { counts, refreshCounts } from "@/notifications"
import { canRead, canRunReport, deskAccess, inTrainingCompany, logout, session, setCompany } from "@/store"
import TrainingLayer from "@/training/TrainingLayer.vue"
import { state } from "@/training/run"

interface NavItem {
	label: string
	to: string
	icon: string
	/** shown only when the user can read this doctype */
	doctype?: string
	/** shown only when the user can run this report */
	report?: string
}

const NAV: { label: string; items: NavItem[] }[] = [
	{
		label: "",
		items: [
			{ label: "Dashboard", to: "/", icon: "lucide-layout-dashboard" },
			{ label: "Approvals", to: "/approvals", icon: "lucide-shield-check" },
			{ label: "Notifications", to: "/notifications", icon: "lucide-bell" },
			{ label: "Training", to: "/training", icon: "lucide-graduation-cap" },
		],
	},
	{
		label: "Accounts",
		items: [
			{ label: "Expenses", to: "/expenses", icon: "lucide-receipt", doctype: "Journal Entry" },
			{ label: "Journal Entries", to: "/journals", icon: "lucide-book-open", doctype: "Journal Entry" },
			{ label: "Expense Accounts", to: "/accounts", icon: "lucide-list-tree", doctype: "Account" },
			{ label: "Cost Centers", to: "/cost-centers", icon: "lucide-network", doctype: "Cost Center" },
			{ label: "General Ledger", to: "/reports/general-ledger", icon: "lucide-book-text", report: "General Ledger" },
		],
	},
	{
		label: "Purchasing",
		items: [
			{ label: "Suppliers", to: "/suppliers", icon: "lucide-users", doctype: "Supplier" },
			{ label: "Bills", to: "/bills", icon: "lucide-file-text", doctype: "Purchase Invoice" },
			{ label: "Items", to: "/items", icon: "lucide-package", doctype: "Item" },
			{ label: "Item Groups", to: "/item-groups", icon: "lucide-folder-tree", doctype: "Item Group" },
			{ label: "Payments", to: "/payments", icon: "lucide-banknote", doctype: "Supplier Payment" },
			{ label: "Recurring", to: "/recurring", icon: "lucide-repeat", doctype: "Recurring Payment" },
		],
	},
	{
		label: "Projects",
		items: [
			{ label: "Projects", to: "/projects", icon: "lucide-folder-kanban", doctype: "Project" },
			{ label: "Tasks", to: "/tasks", icon: "lucide-list-checks", doctype: "Task" },
			{ label: "Expense Categories", to: "/categories", icon: "lucide-tags", doctype: "Expense Category" },
		],
	},
	{ label: "Budgeting", items: [{ label: "Budgets", to: "/budgets", icon: "lucide-piggy-bank", doctype: "Budget" }] },
	{ label: "Assets", items: [{ label: "Assets", to: "/assets", icon: "lucide-laptop", doctype: "Asset" }] },
	{
		label: "Setup",
		items: [
			{ label: "Reports", to: "/reports", icon: "lucide-chart-column" },
			{ label: "Settings", to: "/settings", icon: "lucide-settings", doctype: "Spend Settings" },
		],
	},
]

// each module shows only what the user's roles allow; a module with nothing left is hidden
const visibleNav = computed(() =>
	NAV.map((group) => ({ ...group, items: group.items.filter(isVisible) })).filter((group) => group.items.length),
)

function isVisible(item: NavItem) {
	if (item.doctype) return canRead(item.doctype)
	if (item.report) return canRunReport(item.report)
	if (item.to === "/reports") return session.reports.length > 0
	return true
}

const route = useRoute()
const menuOpen = ref(false)
// from Frappe's logo settings; the wallet icon shows if the image does not load
const appLogo = ref(window.app_logo || "")
const badges = computed<Record<string, number>>(() => ({ "/approvals": counts.pending, "/notifications": counts.unread }))

// counts refresh on navigation and every minute
let timer: ReturnType<typeof setInterval> | undefined
onMounted(() => {
	refreshCounts()
	timer = setInterval(refreshCounts, 60000)
})
onBeforeUnmount(() => clearInterval(timer))
watch(() => [route.path, session.company], refreshCounts)

function isActive(to: string) {
	return to === "/" ? route.path === "/" : route.path.startsWith(to)
}

function switchCompany(name: string) {
	setCompany(name)
}

/** `/bills` → `nav.bills`, `/` → `nav.dashboard`: what training steps point at. */
function navKey(to: string) {
	return `nav.${to.slice(1).replaceAll("/", ".") || "dashboard"}`
}

function leaveTraining() {
	const real = session.companies.find((c) => !c.is_training)
	if (real) setCompany(real.name)
}
</script>
