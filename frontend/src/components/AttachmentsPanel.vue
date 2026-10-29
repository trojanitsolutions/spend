<template>
	<section class="card p-4">
		<div class="mb-3 flex items-center justify-between gap-2">
			<h2 class="text-base font-semibold">
				Attachments
				<span v-if="files?.length" class="ml-1 text-sm font-normal text-ink-gray-5">{{ files.length }}</span>
			</h2>
			<FileUploader :doctype="doctype" :docname="name" :private="true" @success="uploaded">
				<template #default="{ openFileSelector, uploading, progress, error }">
					<Button size="sm" icon-left="lucide-paperclip" :loading="uploading" :label="uploading ? `${progress}%` : 'Attach file'" @click="openFileSelector" />
					<p v-if="error" class="mt-1 text-xs text-ink-red-4">{{ error }}</p>
				</template>
			</FileUploader>
		</div>

		<div v-if="!files" class="py-2"><LoadingText /></div>
		<p v-else-if="!files.length" class="py-4 text-center text-sm text-ink-gray-5">No files attached</p>
		<ul v-else class="-mx-2 space-y-0.5">
			<li v-for="f in files" :key="f.name" class="group flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-surface-gray-2">
				<span :class="[iconOf(f.file_name), 'size-4 shrink-0 text-ink-gray-5']" aria-hidden="true" />
				<div class="min-w-0 flex-1">
					<a :href="f.file_url" target="_blank" rel="noopener" class="block truncate text-sm font-medium text-ink-gray-8 hover:underline" :title="f.file_name">
						{{ f.file_name }}
					</a>
					<div class="truncate text-xs text-ink-gray-5">{{ size(f.file_size) }} · {{ f.owner_name }}</div>
				</div>
				<Button
					v-if="f.can_remove"
					size="sm"
					variant="ghost"
					icon="lucide-trash-2"
					:aria-label="`Remove ${f.file_name}`"
					class="shrink-0 opacity-100 xl:opacity-0 xl:group-hover:opacity-100 xl:focus:opacity-100"
					@click="remove(f)"
				/>
			</li>
		</ul>
	</section>
</template>

<script setup lang="ts">
import { Button, dialog, FileUploader, LoadingText, toast } from "frappe-ui"
import { api, type Attachment } from "@/api"

const props = defineProps<{ doctype: string; name: string; files?: Attachment[] }>()
const emit = defineEmits<{ changed: [] }>()

const ICONS: [RegExp, string][] = [
	[/\.(png|jpe?g|gif|webp|svg|heic)$/i, "lucide-image"],
	[/\.pdf$/i, "lucide-file-text"],
	[/\.(xlsx?|csv|ods)$/i, "lucide-file-spreadsheet"],
	[/\.(zip|rar|7z|gz)$/i, "lucide-file-archive"],
]

function iconOf(fileName: string) {
	return ICONS.find(([pattern]) => pattern.test(fileName))?.[1] || "lucide-file"
}

function size(bytes: number) {
	if (!bytes) return "—"
	if (bytes < 1024) return `${bytes} B`
	if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
	return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function uploaded(file: { file_name: string }) {
	toast.success(`${file.file_name} attached`)
	emit("changed")
}

function remove(file: Attachment) {
	dialog.confirm({
		title: `Remove ${file.file_name}?`,
		message: "The file is deleted and can no longer be opened from this document.",
		confirmLabel: "Remove",
		theme: "red",
		onConfirm: async () => {
			await api("spend.spend.activity.remove_attachment", { doctype: props.doctype, name: props.name, file: file.name })
			toast.success(`${file.file_name} removed`)
			emit("changed")
		},
	})
}
</script>
