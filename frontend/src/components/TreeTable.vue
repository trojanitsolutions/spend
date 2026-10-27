<template>
	<DataTable :columns="allColumns" :rows="shown" :row-key="nameField" :loading="loading" empty-text="Nothing to show">
		<template #[nameField]="{ row }">
			<div class="flex items-center gap-1" :style="{ paddingLeft: `${(row.indent || 0) * 1.25}rem` }">
				<button
					v-if="hasChildren.has(row[nameField])"
					type="button"
					class="flex size-5 items-center justify-center rounded text-ink-gray-5 hover:bg-surface-gray-2"
					:aria-expanded="!collapsed.has(row[nameField])"
					:aria-label="`${collapsed.has(row[nameField]) ? 'Expand' : 'Collapse'} ${row[nameField]}`"
					@click.stop="$emit('toggle', row[nameField])"
				>
					<span :class="[collapsed.has(row[nameField]) ? 'lucide-chevron-right' : 'lucide-chevron-down', 'size-3.5']" aria-hidden="true" />
				</button>
				<span v-else class="w-5" />
				<span :class="row.is_group ? 'font-medium text-ink-gray-9' : 'text-ink-gray-7'">{{ label ? label(row) : row[nameField] }}</span>
			</div>
		</template>
		<template v-for="col in columns" :key="col.key" #[col.key]="{ row, value }">
			<slot :name="col.key" :row="row" :value="value">
				<span :class="{ 'font-medium': row.is_group }">{{ col.format ? col.format(value, row) : value }}</span>
			</slot>
		</template>
	</DataTable>
</template>

<script setup lang="ts">
import { computed } from "vue"
import DataTable, { type Column } from "./DataTable.vue"

const props = defineProps<{
	rows: Record<string, any>[]
	columns: Column[]
	nameField: string
	parentField: string
	collapsed: Set<string>
	loading?: boolean
	nameLabel?: string
	label?: (row: Record<string, any>) => string
}>()

defineEmits<{ toggle: [name: string] }>()

const allColumns = computed<Column[]>(() => [{ key: props.nameField, label: props.nameLabel || "Name" }, ...props.columns])

const hasChildren = computed(() => new Set(props.rows.map((r) => r[props.parentField]).filter(Boolean)))

// hide every row with a collapsed ancestor
const shown = computed(() => {
	const hidden = new Set<string>()
	return props.rows.filter((row) => {
		const parent = row[props.parentField]
		if (parent && (hidden.has(parent) || props.collapsed.has(parent))) {
			hidden.add(row[props.nameField])
			return false
		}
		return true
	})
})
</script>
