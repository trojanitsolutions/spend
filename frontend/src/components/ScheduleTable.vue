<template>
	<div class="space-y-2">
		<div v-for="(row, i) in rows" :key="row.key" class="grid grid-cols-[1fr_10rem_auto] items-end gap-2">
			<FormControl v-model="row.payment_date" type="date" :label="i === 0 ? 'Date' : undefined" :aria-label="`Date ${i + 1}`" />
			<FormControl v-model="row.amount" type="number" min="0" step="0.01" :label="i === 0 ? 'Amount' : undefined" :placeholder="placeholder" :aria-label="`Amount ${i + 1}`" />
			<Button variant="ghost" icon="lucide-trash-2" :aria-label="`Remove date ${i + 1}`" @click="rows.splice(i, 1)" />
		</div>
		<div class="flex flex-wrap items-center justify-between gap-2 pt-1">
			<Button variant="subtle" icon-left="lucide-plus" label="Add date" @click="addRow()" />
			<slot />
		</div>
	</div>
</template>

<script lang="ts">
export interface ScheduleRow {
	key: number
	payment_date: string
	amount: number | string
}

let nextKey = 1

/** A new row for the schedule table. */
export function scheduleRow(payment_date = "", amount: number | string = ""): ScheduleRow {
	return { key: nextKey++, payment_date, amount }
}
</script>

<script setup lang="ts">
import { Button, FormControl } from "frappe-ui"

// rows are edited in place; `amount` may be left blank when the placeholder says what it becomes
const props = defineProps<{ rows: ScheduleRow[]; placeholder?: string; defaultAmount?: number | string }>()

function addRow() {
	props.rows.push(scheduleRow("", props.defaultAmount ?? ""))
}
</script>
