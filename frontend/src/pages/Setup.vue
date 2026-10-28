<template>
	<main class="flex min-h-screen items-center justify-center bg-surface-gray-1 px-4 py-10">
		<form class="w-full max-w-md space-y-5 rounded-2xl border border-outline-gray-1 bg-surface-base p-6 shadow-sm sm:p-8" @submit.prevent="create">
			<div class="space-y-2">
				<img v-if="appLogo" :src="appLogo" alt="" class="size-10 rounded-lg" />
				<h1 class="text-xl font-semibold text-ink-gray-9">Set up Spend</h1>
				<p class="text-base text-ink-gray-6">Add your company to start tracking spend.</p>
			</div>

			<FormControl v-model="companyName" label="Company name" placeholder="Trojan IT Solutions" required autofocus />
			<FormControl
				:model-value="abbr"
				label="Abbreviation"
				placeholder="TIS"
				description="Added to account and cost center names, like Cash - TIS."
				required
				@update:model-value="editAbbr"
			/>
			<LinkField v-model="currency" doctype="Currency" label="Currency" :filters="{ enabled: 1 }" required />

			<p class="text-sm text-ink-gray-5">Spend creates a standard chart of accounts and cost centers for this company.</p>
			<p v-if="error" class="text-sm text-ink-red-4" role="alert">{{ error }}</p>

			<Button type="submit" variant="solid" class="w-full" label="Create company" :loading="saving" :disabled="!ready" />
			<p class="text-center text-sm text-ink-gray-5">
				Signed in as {{ session.fullName || session.user }}.
				<button type="button" class="font-medium text-ink-gray-7 underline-offset-2 hover:underline" @click="logout">Log out</button>
			</p>
		</form>
	</main>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { Button, FormControl, toast } from "frappe-ui"
import LinkField from "@/components/LinkField.vue"
import { api, errorMessage } from "@/api"
import { logout, reloadSession, session, setCompany } from "@/store"

const router = useRouter()
const appLogo = window.app_logo || ""

const companyName = ref("")
const abbr = ref("")
const currency = ref(session.defaultCurrency)
const saving = ref(false)
const error = ref("")
let abbrEdited = false

/** "Trojan IT Solutions" → "TIS" */
function abbrOf(name: string) {
	return name
		.split(/\s+/)
		.filter(Boolean)
		.map((word) => word[0].toUpperCase())
		.join("")
}

// the abbreviation follows the name until it is typed by hand
watch(companyName, (name) => {
	if (!abbrEdited) abbr.value = abbrOf(name)
})

function editAbbr(value: string) {
	abbr.value = value.toUpperCase()
	abbrEdited = Boolean(value)
}

const ready = computed(() => companyName.value.trim() && abbr.value.trim() && currency.value)

async function create() {
	if (!ready.value || saving.value) return
	saving.value = true
	error.value = ""
	try {
		const { name } = await api(
			"spend.spend.setup.setup_company",
			{ company_name: companyName.value, abbr: abbr.value, currency: currency.value },
			{ silent: true },
		)
		await reloadSession()
		setCompany(name)
		await router.replace("/")
		toast.success(`${name} is ready`)
	} catch (e) {
		error.value = errorMessage(e)
	} finally {
		saving.value = false
	}
}
</script>
