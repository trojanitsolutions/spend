<template>
	<Dialog v-model:open="open" title="When was it done?" :actions="[{ label: 'Mark Completed', variant: 'solid', loading: saving, onClick: complete }]">
		<form class="space-y-2" @submit.prevent="complete">
			<FormControl v-model="completedOn" type="date" label="Completed on" required :max="today()" />
			<p v-if="tasks.length > 1" class="text-sm text-ink-gray-5">{{ tasks.length }} tasks are marked completed on this date.</p>
		</form>
	</Dialog>
</template>

<script setup lang="ts">
import { ref, watch } from "vue"
import { Dialog, FormControl, toast } from "frappe-ui"
import { api } from "@/api"
import { today } from "@/format"

const props = defineProps<{ tasks: string[] }>()
const emit = defineEmits<{ done: [] }>()
const open = defineModel<boolean>("open", { default: false })

const saving = ref(false)
const completedOn = ref(today())

watch(open, (value) => value && (completedOn.value = today()))

async function complete() {
	if (!completedOn.value) {
		toast.error("Enter the date it was done")
		return
	}
	if (completedOn.value > today()) {
		toast.error("The date cannot be in the future")
		return
	}
	saving.value = true
	try {
		await api("spend.projects.doctype.task.task.set_multiple_status", { names: props.tasks, status: "Completed", completed_on: completedOn.value })
		toast.success(props.tasks.length > 1 ? "Tasks completed" : "Task completed")
		emit("done")
		open.value = false
	} finally {
		saving.value = false
	}
}
</script>
