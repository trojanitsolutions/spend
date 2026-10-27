<template>
	<Combobox
		:model-value="modelValue || null"
		:options="options"
		:label="label"
		:required="required"
		:placeholder="placeholder || `Select ${doctype}`"
		:filterable="false"
		:loading="loading"
		:description="description"
		@update:query="search"
		@update:open="(open: boolean) => open && search('')"
		@update:model-value="(v: any) => emit('update:modelValue', v ?? '')"
	/>
</template>

<script setup lang="ts">
import { ref, watch } from "vue"
import { Combobox, debounce } from "frappe-ui"
import { searchLink } from "@/api"

const props = defineProps<{
	doctype: string
	modelValue?: string
	label?: string
	placeholder?: string
	description?: string
	required?: boolean
	filters?: Record<string, any>
	query?: string
}>()

const emit = defineEmits<{ "update:modelValue": [value: string] }>()

const options = ref<{ label: string; value: string; description?: string }[]>([])
const loading = ref(false)

const search = debounce(async (txt: string) => {
	loading.value = true
	try {
		const results = await searchLink(props.doctype, txt || "", props.filters || {}, props.query)
		options.value = results.map((r) => ({ label: r.label || r.value, value: r.value, description: r.description }))
		ensureCurrent()
	} finally {
		loading.value = false
	}
}, 200)

// keep the selected value resolvable even before the first search
function ensureCurrent() {
	if (props.modelValue && !options.value.some((o) => o.value === props.modelValue)) {
		options.value.unshift({ label: props.modelValue, value: props.modelValue })
	}
}

watch(() => props.modelValue, ensureCurrent, { immediate: true })
watch(() => JSON.stringify(props.filters), () => search(""))
</script>
