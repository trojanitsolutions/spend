<template>
	<Dialog v-model:open="open" :title="title" :actions="actions">
		<form class="space-y-3" @submit.prevent="move(target || project)">
			<template v-if="target">
				<p class="text-sm text-ink-gray-6">Pick a submitted asset that is not on a project. Depreciation from the allocation date on is charged to <span class="font-medium text-ink-gray-9">{{ target }}</span>.</p>
				<LinkField v-model="picked" doctype="Asset" label="Asset" :filters="{ company: session.company, docstatus: 1, project: ['is', 'not set'] }" />
			</template>
			<template v-else>
				<p v-if="current" class="text-sm text-ink-gray-6">Now on project <span class="font-medium text-ink-gray-9">{{ current }}</span>. Depreciation from the move date on is charged to the new project.</p>
				<LinkField v-model="project" doctype="Project" label="New project" :filters="{ company: session.company, status: 'Open', name: ['!=', current || ''] }" />
			</template>
			<FormControl v-model="moveDate" type="date" :label="target ? 'Allocated on' : 'Moved on'" required :max="today()" />
			<FormControl v-model="reason" type="textarea" label="Reason" placeholder="e.g. Project completed" />
		</form>
	</Dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { Dialog, FormControl, toast } from "frappe-ui"
import LinkField from "@/components/LinkField.vue"
import { api } from "@/api"
import { today } from "@/format"
import { session } from "@/store"

// `target` without `asset` allocates a picked asset to that project
const props = defineProps<{ asset?: string; current?: string | null; target?: string }>()
const emit = defineEmits<{ done: [] }>()
const open = defineModel<boolean>("open", { default: false })

const saving = ref(false)
const picked = ref("")
const project = ref("")
const moveDate = ref(today())
const reason = ref("")

watch(open, (value) => {
	if (!value) return
	picked.value = ""
	project.value = ""
	moveDate.value = today()
	reason.value = ""
})

const title = computed(() => (props.target ? `Allocate asset to ${props.target}` : props.current ? "Move asset" : "Assign to a project"))

const actions = computed(() =>
	props.target
		? [{ label: "Allocate", variant: "solid", loading: saving.value, disabled: !picked.value, onClick: () => move(props.target!) }]
		: [
				{ label: props.current ? "Move" : "Assign", variant: "solid", loading: saving.value, disabled: !project.value, onClick: () => move(project.value) },
				...(props.current ? [{ label: "Remove from project", theme: "red", loading: saving.value, disabled: !!project.value, onClick: () => move("") }] : []),
			],
)

async function move(to: string) {
	const asset = props.target ? picked.value : props.asset
	if (!asset) {
		toast.error("Pick an asset")
		return
	}
	if (!moveDate.value) {
		toast.error("Enter the date of the move")
		return
	}
	saving.value = true
	try {
		await api("spend.assets.doctype.asset.asset.move_asset", { asset, project: to || null, date: moveDate.value, reason: reason.value })
		toast.success(props.target ? `${asset} allocated to ${to}` : to ? `Moved to ${to}` : "Removed from the project")
		emit("done")
		open.value = false
	} finally {
		saving.value = false
	}
}
</script>
