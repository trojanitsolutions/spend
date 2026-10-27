import { createApp } from "vue"
import { setConfig, toast } from "frappe-ui"
import App from "./App.vue"
import router from "./router"
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

// the tab icon follows the favicon set in Frappe's Website Settings
if (window.favicon) {
	const link = document.querySelector<HTMLLinkElement>("link[rel='icon']") ?? document.head.appendChild(document.createElement("link"))
	link.rel = "icon"
	link.href = window.favicon
}

createApp(App).use(router).mount("#app")
