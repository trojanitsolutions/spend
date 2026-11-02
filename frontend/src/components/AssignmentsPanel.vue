<template>
	<section class="card p-4">
		<div class="mb-3 flex items-center justify-between gap-2">
			<h2 class="text-base font-semibold">
				Assigned to
				<span v-if="users?.length" class="ml-1 text-sm font-normal text-ink-gray-5">{{ users.length }}</span>
			</h2>
			<Button v-if="canAssign && !adding" size="sm" icon-left="lucide-user-plus" label="Assign" @click="adding = true" />
		</div>

		<div v-if="adding" class="mb-3 flex items-center gap-2">
			<LinkField
				:key="users?.length"
				class="min-w-0 flex-1"
				doctype="User"
				placeholder="Pick a user"
				:filters="{ enabled: 1, user_type: 'System User', name: ['not in', users?.map((u) => u.user) || []] }"
				@update:model-value="add"
			/>
			<Button size="sm" variant="ghost" icon="lucide-x" aria-label="Close" @click="adding = false" />
		</div>

		<div v-if="!users" class="py-2"><LoadingText /></div>
		<p v-else-if="!users.length" class="py-4 text-center text-sm text-ink-gray-5">Not assigned to anyone</p>
		<ul v-else class="-mx-2 space-y-0.5">
			<li v-for="u in users" :key="u.user" class="group flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-surface-gray-2">
				<Avatar size="md" :label="u.full_name" :image="u.user_image || undefined" />
				<div class="min-w-0 flex-1">
					<div class="truncate text-sm font-medium text-ink-gray-8" :title="u.full_name">{{ u.full_name }}</div>
					<div class="truncate text-xs text-ink-gray-5">{{ u.user }}</div>
				</div>
				<Button
					v-if="canAssign"
					size="sm"
					variant="ghost"
					icon="lucide-x"
					:aria-label="`Unassign ${u.full_name}`"
					class="shrink-0 opacity-100 xl:opacity-0 xl:group-hover:opacity-100 xl:focus:opacity-100"
					@click="remove(u)"
				/>
			</li>
		</ul>
	</section>
</template>

<script setup lang="ts">
import { ref } from "vue"
import { Avatar, Button, LoadingText, toast } from "frappe-ui"
import LinkField from "@/components/LinkField.vue"
import { api, type Assignee } from "@/api"

const props = defineProps<{ doctype: string; name: string; users?: Assignee[]; canAssign?: boolean }>()
const emit = defineEmits<{ changed: [] }>()

const adding = ref(false)

// assigning adds a ToDo for the user and notifies them, as Desk's "Assign To" does
async function add(user: string) {
	if (!user) return
	await api("frappe.desk.form.assign_to.add", { doctype: props.doctype, name: props.name, assign_to: [user] })
	toast.success("Assigned")
	adding.value = false
	emit("changed")
}

async function remove(u: Assignee) {
	await api("frappe.desk.form.assign_to.remove", { doctype: props.doctype, name: props.name, assign_to: u.user })
	toast.success(`${u.full_name} unassigned`)
	emit("changed")
}
</script>
