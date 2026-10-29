import { createApp } from "vue"
import { setConfig, toast } from "frappe-ui"
import App from "./App.vue"
import router from "./router"
import { applyTheme } from "./theme"
import { vTour } from "./training/tour"
import "./style.css"

// non-blocking server messages (e.g. "budget exceeded" warnings) become toasts
setConfig("serverMessagesHandler", (messages: string[]) => {
	for (const raw of messages) {
		let message = raw
		let indicator = ""
		try {
			const parsed = JSON.parse(raw)
			message = parsed.message
			indicator = parsed.indicator
		} catch {
			// plain string message
		}
		const text = String(message).replace(/<[^>]+>/g, "")
		indicator === "orange" || indicator === "red" ? toast.warning(text) : toast.info(text)
	}
})

// the active Frontend Template, applied before mount so the default look never flashes
applyTheme(window.theme)

createApp(App).use(router).directive("tour", vTour).mount("#app")
