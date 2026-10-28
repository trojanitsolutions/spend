import { createRouter, createWebHistory } from "vue-router"
import { canRead, canRunReport, loadSession, session } from "./store"
import { REPORTS } from "./reports"

const router = createRouter({
	history: createWebHistory("/spend"),
	routes: [
		{ path: "/", name: "Dashboard", component: () => import("@/pages/Dashboard.vue") },
		{ path: "/assets", name: "Assets", component: () => import("@/pages/Assets.vue"), meta: { doctype: "Asset" } },
		{ path: "/assets/new", name: "AssetNew", component: () => import("@/pages/AssetNew.vue"), meta: { doctype: "Asset" } },
		{ path: "/assets/:name", name: "AssetDetail", component: () => import("@/pages/AssetDetail.vue"), props: true, meta: { doctype: "Asset" } },
		{ path: "/budgets", name: "Budgets", component: () => import("@/pages/Budgets.vue"), meta: { doctype: "Budget" } },
		{ path: "/budgets/new", name: "BudgetNew", component: () => import("@/pages/BudgetNew.vue"), meta: { doctype: "Budget" } },
		{ path: "/budgets/:name", name: "BudgetDetail", component: () => import("@/pages/BudgetDetail.vue"), props: true, meta: { doctype: "Budget" } },
		{ path: "/expenses", name: "Expenses", component: () => import("@/pages/Entries.vue"), props: { kind: "expense" }, meta: { doctype: "Journal Entry" } },
		{ path: "/expenses/new", name: "ExpenseNew", component: () => import("@/pages/EntryNew.vue"), props: { kind: "expense" }, meta: { doctype: "Journal Entry" } },
		{ path: "/expenses/:name", name: "ExpenseDetail", component: () => import("@/pages/EntryDetail.vue"), props: true, meta: { doctype: "Journal Entry" } },
		{ path: "/journals", name: "Journals", component: () => import("@/pages/Entries.vue"), props: { kind: "journal" }, meta: { doctype: "Journal Entry" } },
		{ path: "/journals/new", name: "JournalNew", component: () => import("@/pages/EntryNew.vue"), props: { kind: "journal" }, meta: { doctype: "Journal Entry" } },
		{ path: "/journals/:name", name: "JournalDetail", component: () => import("@/pages/EntryDetail.vue"), props: true, meta: { doctype: "Journal Entry" } },
		// old links
		{ path: "/entries", redirect: "/expenses" },
		{ path: "/entries/new", redirect: (to) => ({ path: "/expenses/new", query: to.query }) },
		{ path: "/entries/:name", name: "EntryDetail", component: () => import("@/pages/EntryDetail.vue"), props: true, meta: { doctype: "Journal Entry" } },
		{ path: "/suppliers", name: "Suppliers", component: () => import("@/pages/Suppliers.vue"), meta: { doctype: "Supplier" } },
		{ path: "/suppliers/:name", name: "SupplierDetail", component: () => import("@/pages/SupplierDetail.vue"), props: true, meta: { doctype: "Supplier" } },
		{ path: "/items", name: "Items", component: () => import("@/pages/Items.vue"), meta: { doctype: "Item" } },
		{ path: "/items/new", name: "ItemNew", component: () => import("@/pages/ItemForm.vue"), meta: { doctype: "Item" } },
		{ path: "/items/:name", name: "ItemDetail", component: () => import("@/pages/ItemForm.vue"), props: true, meta: { doctype: "Item" } },
		{ path: "/item-groups", name: "ItemGroups", component: () => import("@/pages/ItemGroups.vue"), meta: { doctype: "Item Group" } },
		{ path: "/bills", name: "PurchaseInvoices", component: () => import("@/pages/PurchaseInvoices.vue"), meta: { doctype: "Purchase Invoice" } },
		{ path: "/bills/new", name: "PurchaseInvoiceNew", component: () => import("@/pages/PurchaseInvoiceNew.vue"), meta: { doctype: "Purchase Invoice" } },
		{ path: "/bills/:name", name: "PurchaseInvoiceDetail", component: () => import("@/pages/PurchaseInvoiceDetail.vue"), props: true, meta: { doctype: "Purchase Invoice" } },
		{ path: "/payments", name: "Payments", component: () => import("@/pages/Payments.vue"), meta: { doctype: "Supplier Payment" } },
		{ path: "/payments/new", name: "PaymentNew", component: () => import("@/pages/PaymentNew.vue"), meta: { doctype: "Supplier Payment" } },
		{ path: "/payments/:name", name: "PaymentDetail", component: () => import("@/pages/PaymentDetail.vue"), props: true, meta: { doctype: "Supplier Payment" } },
		{ path: "/projects", name: "Projects", component: () => import("@/pages/Projects.vue"), meta: { doctype: "Project" } },
		{ path: "/projects/new", name: "ProjectNew", component: () => import("@/pages/ProjectNew.vue"), meta: { doctype: "Project" } },
		{ path: "/projects/:name", name: "ProjectDetail", component: () => import("@/pages/ProjectDetail.vue"), props: true, meta: { doctype: "Project" } },
		{ path: "/categories", name: "ExpenseCategories", component: () => import("@/pages/ExpenseCategories.vue"), meta: { doctype: "Expense Category" } },
		{ path: "/tasks", name: "Tasks", component: () => import("@/pages/Tasks.vue"), meta: { doctype: "Task" } },
		{ path: "/tasks/new", name: "TaskNew", component: () => import("@/pages/TaskForm.vue"), meta: { doctype: "Task" } },
		{ path: "/tasks/:name", name: "TaskDetail", component: () => import("@/pages/TaskForm.vue"), props: true, meta: { doctype: "Task" } },
		{ path: "/recurring", name: "RecurringPayments", component: () => import("@/pages/RecurringPayments.vue"), meta: { doctype: "Recurring Payment" } },
		{ path: "/recurring/new", name: "RecurringPaymentNew", component: () => import("@/pages/RecurringPaymentNew.vue"), meta: { doctype: "Recurring Payment" } },
		{ path: "/recurring/:name", name: "RecurringPaymentDetail", component: () => import("@/pages/RecurringPaymentDetail.vue"), props: true, meta: { doctype: "Recurring Payment" } },
		{ path: "/accounts", name: "Accounts", component: () => import("@/pages/Accounts.vue"), meta: { doctype: "Account" } },
		{ path: "/cost-centers", name: "CostCenters", component: () => import("@/pages/CostCenters.vue"), meta: { doctype: "Cost Center" } },
		{ path: "/reports", name: "Reports", component: () => import("@/pages/Reports.vue"), meta: { report: true } },
		{ path: "/reports/:slug", name: "ReportView", component: () => import("@/pages/ReportView.vue"), props: true, meta: { report: true } },
		{ path: "/approvals", name: "Approvals", component: () => import("@/pages/Approvals.vue") },
		{ path: "/notifications", name: "Notifications", component: () => import("@/pages/Notifications.vue") },
		{ path: "/settings", name: "Settings", component: () => import("@/pages/Settings.vue"), meta: { doctype: "Spend Settings" } },
		{ path: "/training", name: "Training", component: () => import("@/pages/Training.vue") },
		{ path: "/training/team", name: "TrainingTeam", component: () => import("@/pages/TrainingTeam.vue"), meta: { trainer: true } },
		{ path: "/training/:scenario/edit", name: "TrainingEdit", component: () => import("@/pages/TrainingEdit.vue"), props: true, meta: { trainer: true } },
		{ path: "/:pathMatch(.*)*", redirect: "/" },
	],
})

// hide pages the user has no access to, even when opened by URL; the server still checks DocPerm
router.beforeEach(async (to) => {
	await loadSession()
	if (session.error || to.path === "/") return
	const { doctype, report } = to.meta as { doctype?: string; report?: boolean }
	if (doctype && !canRead(doctype)) return "/"
	if (to.meta.trainer && !session.isTrainer) return "/training"
	if (report) {
		const slug = to.params.slug
		const allowed = slug ? canRunReport(REPORTS.find((r) => r.slug === slug)?.name || "") : session.reports.length > 0
		if (!allowed) return "/"
	}
})

export default router
