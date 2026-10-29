import { today } from "./format"

export interface ReportFilter {
	fieldname: string
	label: string
	type: "date" | "select" | "check" | "link" | "fiscal_year" | "text"
	options?: string[]
	doctype?: string
	linkFilters?: (company: string) => Record<string, any>
	default?: () => any
}

export interface ReportDef {
	slug: string
	name: string
	description: string
	icon: string
	group: "Assets" | "Budgets & Spending" | "Projects" | "Purchasing" | "Accounting"
	filters: ReportFilter[]
}

const asOn: ReportFilter = { fieldname: "as_on_date", label: "As on", type: "date", default: today }
const costCenter: ReportFilter = {
	fieldname: "cost_center",
	label: "Cost center",
	type: "link",
	doctype: "Cost Center",
	linkFilters: (company) => ({ company }),
}
const fiscalYear: ReportFilter = { fieldname: "fiscal_year", label: "Fiscal year", type: "fiscal_year" }
const asset: ReportFilter = {
	fieldname: "asset",
	label: "Asset",
	type: "link",
	doctype: "Asset",
	linkFilters: (company) => ({ company, docstatus: 1 }),
}

export const REPORTS: ReportDef[] = [
	{
		slug: "asset-register",
		name: "Asset Register",
		description: "Every asset with gross value, accumulated depreciation and book value",
		icon: "lucide-clipboard-list",
		group: "Assets",
		filters: [asOn, { fieldname: "status", label: "Status", type: "select", options: ["", "Submitted", "Partially Depreciated", "Fully Depreciated", "Cancelled"] }, costCenter],
	},
	{
		slug: "asset-depreciation-schedule",
		name: "Asset Depreciation Schedule Report",
		description: "Period-by-period schedule with posting status",
		icon: "lucide-calendar-range",
		group: "Assets",
		filters: [asset, { fieldname: "from_date", label: "From", type: "date" }, { fieldname: "to_date", label: "To", type: "date" }, { fieldname: "posting_status", label: "Posting", type: "select", options: ["", "Posted", "Not Posted"] }],
	},
	{
		slug: "depreciation-due",
		name: "Depreciation Due",
		description: "Scheduled depreciation that is due and not yet posted",
		icon: "lucide-calendar-clock",
		group: "Assets",
		filters: [asOn, costCenter],
	},
	{
		slug: "asset-book-value",
		name: "Asset Book Value",
		description: "Book value from the ledger as on any date",
		icon: "lucide-book-open",
		group: "Assets",
		filters: [asOn, costCenter],
	},
	{
		slug: "budget-vs-actual",
		name: "Budget vs Actual",
		description: "Allocated against posted spending, per account",
		icon: "lucide-scale",
		group: "Budgets & Spending",
		filters: [fiscalYear, costCenter, { fieldname: "period", label: "Period", type: "select", options: ["Yearly", "Monthly"], default: () => "Yearly" }],
	},
	{
		slug: "budget-utilization",
		name: "Budget Utilization",
		description: "Utilization and status of each budget",
		icon: "lucide-gauge",
		group: "Budgets & Spending",
		filters: [fiscalYear, costCenter],
	},
	{
		slug: "cost-center-wise-spending",
		name: "Cost Center-wise Spending",
		description: "Expense rolled up through the cost center tree",
		icon: "lucide-network",
		group: "Budgets & Spending",
		filters: [{ fieldname: "from_date", label: "From", type: "date" }, { fieldname: "to_date", label: "To", type: "date" }],
	},
	{
		slug: "project-spend",
		name: "Project Spend",
		description: "Budget, spend and amounts owed for each project",
		icon: "lucide-folder-kanban",
		group: "Projects",
		filters: [
			{ fieldname: "project", label: "Project", type: "link", doctype: "Project", linkFilters: (company) => ({ company }) },
			{ fieldname: "status", label: "Status", type: "select", options: ["", "Open", "Completed", "Cancelled"] },
		],
	},
	{
		slug: "project-category-monthly",
		name: "Project Category Monthly",
		description: "What each expense category and sub category charged in each month, quarter or year",
		icon: "lucide-tags",
		group: "Projects",
		filters: [
			fiscalYear,
			{ fieldname: "project", label: "Project", type: "link", doctype: "Project", linkFilters: (company) => ({ company }) },
			{ fieldname: "expense_category", label: "Category", type: "link", doctype: "Expense Category", linkFilters: (company) => ({ company, is_parent_category: 1 }) },
			{ fieldname: "period", label: "Period", type: "select", options: ["Monthly", "Quarterly", "Yearly"], default: () => "Monthly" },
		],
	},
	{
		slug: "supplier-outstanding",
		name: "Supplier Outstanding",
		description: "What is owed to each supplier, with ageing by days overdue",
		icon: "lucide-hourglass",
		group: "Purchasing",
		filters: [
			asOn,
			{ fieldname: "supplier", label: "Supplier", type: "link", doctype: "Supplier", linkFilters: () => ({}) },
			{ fieldname: "show_settled", label: "Show settled suppliers", type: "check" },
		],
	},
	{
		slug: "general-ledger",
		name: "General Ledger",
		description: "Every posted ledger row, newest first, with running and closing balances",
		icon: "lucide-book-text",
		group: "Accounting",
		filters: [
			{ fieldname: "from_date", label: "From", type: "date", default: () => today().slice(0, 8) + "01" },
			{ fieldname: "to_date", label: "To", type: "date", default: today },
			{ fieldname: "account", label: "Account", type: "link", doctype: "Account", linkFilters: (company) => ({ company }) },
			costCenter,
			{ fieldname: "project", label: "Project", type: "link", doctype: "Project", linkFilters: (company) => ({ company }) },
			{ fieldname: "party", label: "Supplier", type: "link", doctype: "Supplier", linkFilters: () => ({}) },
			{ fieldname: "voucher_no", label: "Voucher", type: "text" },
			{ fieldname: "group_by_account", label: "Group by account", type: "check" },
		],
	},
	{
		slug: "chart-of-accounts",
		name: "Chart of Accounts",
		description: "Account tree with debit, credit and balance",
		icon: "lucide-list-tree",
		group: "Accounting",
		filters: [asOn, { fieldname: "root_type", label: "Root type", type: "select", options: ["", "Asset", "Liability", "Equity", "Income", "Expense"] }, { fieldname: "show_zero_balances", label: "Show zero balances", type: "check", default: () => 1 }],
	},
]
