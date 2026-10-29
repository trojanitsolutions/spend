<template>
	<FrappeUIProvider>
		<div v-if="!session.ready" class="flex h-screen items-center justify-center bg-surface-base">
			<LoadingText :text="`Loading ${theme.appTitle}…`" />
		</div>
		<EmptyState
			v-else-if="session.error"
			class="h-screen"
			icon="lucide-lock"
			:title="session.error === 'forbidden' ? 'No access to Spend' : 'Could not load Spend'"
			:message="
				session.error === 'forbidden'
					? 'Ask an administrator for the Accounts Manager role.'
					: 'Check your connection and reload the page.'
			"
		>
			<Button variant="solid" label="Go to Desk" @click="goToDesk" />
			<Button label="Log out" @click="logout" />
		</EmptyState>
		<AppShell v-else-if="session.company">
			<RouterView :key="session.company" />
		</AppShell>
		<Setup v-else-if="session.canSetup" />
		<EmptyState
			v-else
			class="h-screen"
			icon="lucide-building-2"
			title="Spend is not set up yet"
			message="Ask an Accounts Manager to create the company."
		>
			<Button label="Log out" @click="logout" />
		</EmptyState>
	</FrappeUIProvider>
</template>

<script setup lang="ts">
import { onMounted } from "vue"
import { Button, FrappeUIProvider, LoadingText } from "frappe-ui"
import AppShell from "@/components/AppShell.vue"
import EmptyState from "@/components/EmptyState.vue"
import Setup from "@/pages/Setup.vue"
import { loadSession, logout, session } from "@/store"
import { theme } from "@/theme"

onMounted(loadSession)

function goToDesk() {
	window.location.href = "/app"
}
</script>
