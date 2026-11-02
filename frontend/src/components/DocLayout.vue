<template>
	<!-- a new, unsaved document has nothing to attach or show yet -->
	<div v-if="!name" class="p-4 sm:p-6"><slot /></div>
	<div v-else class="grid grid-cols-1 gap-6 p-4 sm:p-6 xl:grid-cols-[minmax(0,1fr)_18rem]">
		<div class="min-w-0">
			<slot />
		</div>
		<aside class="min-w-0 xl:row-span-2">
			<div class="space-y-6 xl:sticky xl:top-24">
				<AssignmentsPanel
					v-if="assignable"
					:doctype="doctype"
					:name="name"
					:users="activity?.assignments"
					:can-assign="activity?.can_assign"
					@changed="load"
				/>
				<AttachmentsPanel :doctype="doctype" :name="name" :files="activity?.attachments" @changed="load" />
			</div>
		</aside>
		<ActivityPanel class="min-w-0" :doctype="doctype" :name="name" :timeline="activity?.timeline" @changed="load" />
	</div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from "vue"
import ActivityPanel from "@/components/ActivityPanel.vue"
import AssignmentsPanel from "@/components/AssignmentsPanel.vue"
import AttachmentsPanel from "@/components/AttachmentsPanel.vue"
import { getActivity, type Activity } from "@/api"

// `version` is the document's `modified`; a save, submit or approval reloads the activity.
// `assignable` shows who the document is assigned to, as Desk's sidebar does.
const props = defineProps<{ doctype: string; name?: string; version?: string; assignable?: boolean }>()

const activity = ref<Activity | null>(null)

async function load() {
	if (!props.name) return
	activity.value = await getActivity(props.doctype, props.name)
}

watch(() => [props.doctype, props.name, props.version], load)
onMounted(load)
</script>
