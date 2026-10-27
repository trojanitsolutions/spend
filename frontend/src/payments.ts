import { dialog, toast } from "frappe-ui"
import { cancelDoc } from "@/api"

/** Ask, then cancel a submitted Supplier Payment; its bills become unpaid again. */
export function confirmCancelPayment(name: string, onDone: () => unknown) {
	dialog.confirm({
		title: `Cancel payment ${name}?`,
		message: "Its ledger entries are reversed and the bills become unpaid again.",
		confirmLabel: "Cancel Payment",
		theme: "red",
		onConfirm: async () => {
			await cancelDoc("Supplier Payment", name)
			toast.success(`Payment ${name} cancelled`)
			await onDone()
		},
	})
}
