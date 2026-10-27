<template>
	<div class="flex items-end gap-1">
		<LinkField
			class="min-w-0 flex-1"
			:model-value="category"
			doctype="Expense Category"
			:label="labels ? 'Category' : undefined"
			placeholder="Category"
			:query="CATEGORY_QUERY"
			:filters="filters"
			@update:model-value="setCategory"
		/>
		<Button v-if="creatable && !project" variant="ghost" icon="lucide-plus" aria-label="New category" title="New category" @click="creating = 'category'" />
	</div>
	<div class="flex items-end gap-1">
		<LinkField
			class="min-w-0 flex-1"
			:model-value="subCategory"
			doctype="Expense Category"
			:label="labels ? 'Sub category' : undefined"
			:placeholder="category ? 'Sub category (optional)' : 'Pick a category first'"
			:disabled="!category"
			:query="CATEGORY_QUERY"
			:filters="{ ...filters, parent_category: category }"
			@update:model-value="setSubCategory"
		/>
		<Button v-if="creatable" variant="ghost" icon="lucide-plus" :disabled="!category" :aria-label="`New sub category of ${category}`" title="New sub category" @click="creating = 'sub'" />
	</div>
	<CategoryDialog :open="!!creating" :parent="creating === 'sub' ? category : undefined" @update:open="(v) => !v && (creating = null)" @created="useCreated" />
</template>

<script setup lang="ts">
import { computed, ref } from "vue"
import { Button } from "frappe-ui"
import CategoryDialog from "@/components/CategoryDialog.vue"
import LinkField from "@/components/LinkField.vue"
import { CATEGORY_QUERY, getCategoryAccount } from "@/api"
import { can, session } from "@/store"

// `project` limits the choice to the categories picked on that project; a new
// category would not be on it, so there only sub categories can be created
const props = defineProps<{ project?: string; labels?: boolean }>()
const emit = defineEmits<{ account: [account: string] }>()

const category = defineModel<string>("category", { default: "" })
const subCategory = defineModel<string>("subCategory", { default: "" })

const creating = ref<"category" | "sub" | null>(null)
const creatable = computed(() => can("Expense Category", "create"))
const filters = computed(() => ({ company: session.company, ...(props.project ? { project: props.project } : {}) }))

// picking a category fills in its expense account
async function fillAccount() {
	const picked = [category.value, subCategory.value]
	const account = await getCategoryAccount(category.value || undefined, subCategory.value || undefined)
	if (account && picked[0] === category.value && picked[1] === subCategory.value) emit("account", account)
}

function setCategory(value: string) {
	if (value === category.value) return
	category.value = value
	subCategory.value = ""
	if (value) fillAccount()
}

function setSubCategory(value: string) {
	subCategory.value = value
	if (category.value) fillAccount()
}

function useCreated(name: string) {
	if (creating.value === "sub") setSubCategory(name)
	else setCategory(name)
	creating.value = null
}
</script>
