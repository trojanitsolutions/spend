<template>
	<div class="rounded-lg border border-outline-gray-2 bg-surface-base">
		<Editor v-model="model" :extensions="extensions" :upload-function="upload" :placeholder="placeholder">
			<EditorFixedMenu class="border-b border-outline-gray-1 p-1" :items="MENU" size="xs" />
			<EditorContent class="max-h-64 min-h-20 overflow-y-auto px-3 py-2 text-sm" />
		</Editor>
	</div>
</template>

<script setup lang="ts">
import { useFileUpload } from "frappe-ui"
import {
	Bold,
	BulletList,
	CommentKit,
	Editor,
	EditorContent,
	EditorFixedMenu,
	InsertImage,
	InsertLink,
	Italic,
	OrderedList,
	Separator,
} from "frappe-ui/editor"

// Step text: a little formatting, links and images. Images are public so every trainee can see them.
const props = defineProps<{ scenario: string; placeholder?: string }>()
const model = defineModel<string>({ default: "" })

const MENU = [Bold, Italic, Separator, BulletList, OrderedList, Separator, InsertLink, InsertImage]
const extensions = [CommentKit.configure({ mention: false, tag: false, emoji: false, table: false, video: false, attachment: false })]
const uploader = useFileUpload()

function upload(file: File) {
	return uploader.upload(file, { private: false, doctype: "Training Scenario", docname: props.scenario }) as Promise<{
		file_url: string
	}>
}
</script>
