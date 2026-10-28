<template>
	<div class="space-y-3">
		<FormControl v-model="step.title" label="Title" placeholder="What the trainee does, in a few words" @update:model-value="changed" />
		<div class="grid grid-cols-2 gap-3">
			<FormControl v-model="step.action_type" type="select" label="Action" :options="ACTIONS" @update:model-value="changed" />
			<FormControl v-model="step.route" label="Page" placeholder="Any page" @update:model-value="changed" />
		</div>
		<div>
			<div class="mb-1.5 flex items-center gap-2 text-xs text-ink-gray-5">
				Target
				<Badge v-if="step.target_kind === 'Selector'" theme="amber" size="sm" label="Fragile" title="Not a data-tour key: breaks if this part of the page changes" />
			</div>
			<FormControl v-model="step.target" :placeholder="step.action_type === 'Observe' ? 'Optional' : 'Pick an element'" @update:model-value="changed" />
			<p v-if="step.target_label" class="mt-1 text-xs text-ink-gray-5">{{ step.target_label }}</p>
		</div>
		<div>
			<div class="mb-1.5 text-xs text-ink-gray-5">Coach text</div>
			<RichText v-model="step.body" :scenario="scenario" placeholder="What should the trainee do, and why?" @update:model-value="changed" />
		</div>
		<FormControl v-model="step.hint" type="textarea" :rows="2" label="Hint" placeholder="Shown in Guided, and when Practice asks for a hint" @update:model-value="changed" />
		<FormControl
			v-if="step.action_type === 'Enter Value' || step.action_type === 'Select Option'"
			v-model="step.expected_value"
			label="Expected value"
			placeholder="Empty accepts any value"
			description="10, >=2, !=Draft, or a|b"
			@update:model-value="changed"
		/>
	</div>
</template>

<script setup lang="ts">
import { Badge, FormControl } from "frappe-ui"
import type { Step } from "./api"
import RichText from "./RichText.vue"

const ACTIONS = ["Click", "Enter Value", "Select Option", "Observe"]

defineProps<{ scenario: string }>()
const step = defineModel<Step>({ required: true })
const emit = defineEmits<{ change: [] }>()

function changed() {
	emit("change")
}
</script>
