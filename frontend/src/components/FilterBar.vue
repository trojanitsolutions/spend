<template>
	<div class="flex flex-wrap items-end gap-3 px-4 pb-4 pt-1 sm:px-6">
		<template v-for="f in fields" :key="f.key">
			<template v-if="f.type === 'date-range'">
				<FormControl
					class="w-[calc(50%-0.25rem)] sm:w-36"
					type="date"
					:label="`${f.label} from`"
					:model-value="modelValue[`${f.key}_from`]"
					@update:model-value="(v: string) => set(`${f.key}_from`, v)"
				/>
				<FormControl
					class="w-[calc(50%-0.25rem)] sm:w-36"
					type="date"
					label="to"
					:model-value="modelValue[`${f.key}_to`]"
					@update:model-value="(v: string) => set(`${f.key}_to`, v)"
				/>
			</template>
			<FormControl
				v-else-if="f.type === 'select'"
				class="w-full sm:w-40"
				type="select"
				:label="f.label"
				:options="[{ label: 'Any', value: '' }, ...(f.options || []).map((o) => ({ label: o, value: o }))]"
				:model-value="modelValue[f.key]"
				@update:model-value="(v: string) => set(f.key, v)"
			/>
			<LinkField
				v-else
				class="w-full sm:w-48"
				:doctype="f.doctype!"
				:label="f.label"
				:placeholder="`Any ${f.label.toLowerCase()}`"
				:filters="f.filters"
				:model-value="modelValue[f.key]"
				@update:model-value="(v: string) => set(f.key, v)"
			/>
		</template>
		<Button v-if="active" variant="ghost" icon-left="lucide-x" :label="`Clear (${active})`" @click="clear" />
	</div>
</template>

<script setup lang="ts">
import { computed } from "vue"
import { Button, FormControl } from "frappe-ui"
import LinkField from "@/components/LinkField.vue"
import { type FilterField, valueKeys } from "@/filters"

const props = defineProps<{ fields: FilterField[]; modelValue: Record<string, string> }>()

const keys = computed(() => props.fields.flatMap(valueKeys))
const active = computed(() => keys.value.filter((k) => props.modelValue[k]).length)

// the values object is reactive and owned by the page, so it is changed in place
function set(key: string, value: string) {
	props.modelValue[key] = value || ""
}

function clear() {
	for (const k of keys.value) props.modelValue[k] = ""
}
</script>
