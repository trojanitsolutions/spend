<template>
	<div class="overflow-x-auto">
		<table class="w-full min-w-max text-left text-base">
			<thead>
				<tr class="border-b border-outline-gray-1 text-sm text-ink-gray-5">
					<th
						v-for="col in columns"
						:key="col.key"
						scope="col"
						class="whitespace-nowrap px-3 py-2 font-medium first:pl-4 last:pr-4 sm:first:pl-6 sm:last:pr-6"
						:class="{ 'text-right': col.align === 'right' }"
					>
						{{ col.label }}
					</th>
				</tr>
			</thead>
			<tbody>
				<tr v-if="loading && !rows.length">
					<td :colspan="columns.length" class="px-6 py-10 text-center text-ink-gray-5"><LoadingText /></td>
				</tr>
				<tr v-else-if="!rows.length">
					<td :colspan="columns.length" class="px-6 py-10 text-center text-ink-gray-5">{{ emptyText || "Nothing here yet" }}</td>
				</tr>
				<tr
					v-for="(row, i) in rows"
					:key="row[rowKey] ?? i"
					class="border-b border-outline-gray-1 last:border-0"
					:class="[{ 'cursor-pointer hover:bg-surface-gray-1': clickable }, rowClass?.(row)]"
					:tabindex="clickable ? 0 : undefined"
					@click="clickable && $emit('row-click', row)"
					@keydown.enter="clickable && $emit('row-click', row)"
				>
					<td
						v-for="col in columns"
						:key="col.key"
						class="whitespace-nowrap px-3 py-2.5 first:pl-4 last:pr-4 sm:first:pl-6 sm:last:pr-6"
						:class="[{ 'text-right tabular-nums': col.align === 'right' }, col.class]"
					>
						<slot :name="col.key" :row="row" :value="row[col.key]">{{ col.format ? col.format(row[col.key], row) : row[col.key] }}</slot>
					</td>
				</tr>
			</tbody>
		</table>
	</div>
</template>

<script setup lang="ts">
import { LoadingText } from "frappe-ui"

export interface Column {
	key: string
	label: string
	align?: "left" | "right"
	class?: string
	format?: (value: any, row: Record<string, any>) => string
}

withDefaults(
	defineProps<{
		columns: Column[]
		rows: Record<string, any>[]
		rowKey?: string
		loading?: boolean
		clickable?: boolean
		emptyText?: string
		rowClass?: (row: Record<string, any>) => string | undefined
	}>(),
	{ rowKey: "name" },
)

defineEmits<{ "row-click": [row: Record<string, any>] }>()
</script>
