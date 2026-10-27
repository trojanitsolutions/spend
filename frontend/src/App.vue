<template>
	<FrappeUIProvider>
		<div v-if="!session.ready" class="flex h-screen items-center justify-center bg-surface-base">
			<LoadingText text="Loading Spend…" />
		</div>
		<EmptyState
			v-else-if="session.error"
			class="h-screen"
			icon="lucide-lock"
			:title="session.error === 'forbidden' ? 'No access to Spend' : 'Could not load Spend'"
			:message="
				session.error === 'forbidden'
					? 'Ask an administrator for the Accounts User or Accounts Manager role.'
					: 'Check your connection and reload the page.'
			"
		>
			<Button variant="solid" label="Go to Desk" @click="goToDesk" />
		</EmptyState>
		<AppShell v-else>
			<RouterView v-if="session.company" :key="session.company" />
			<EmptyState
				v-else
				icon="lucide-building-2"
				title="Create your first company"
				message="Spend creates a standard chart of accounts and cost center for every new company."
			>
				<Button variant="solid" label="New Company" @click="newCompany" />
			</EmptyState>
		</AppShell>
	</FrappeUIProvider>
</template>

<script setup lang="ts">
import { onMounted } from "vue"
import { Button, FrappeUIProvider, LoadingText } from "frappe-ui"
import AppShell from "@/components/AppShell.vue"
import EmptyState from "@/components/EmptyState.vue"
import { loadSession, session } from "@/store"

onMounted(loadSession)

function goToDesk() {
	window.location.href = "/app"
}

function newCompany() {
	window.location.href = "/app/company/new"
}
</script>
