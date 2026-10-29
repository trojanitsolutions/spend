/// <reference types="vite/client" />

declare module "*.vue" {
	import type { DefineComponent } from "vue"
	const component: DefineComponent
	export default component
}

interface Window {
	/** from Frappe's logo settings, set by spend/www/spend.py */
	favicon?: string
	app_logo?: string
	/** the active Frontend Template, set by spend/www/spend.py */
	theme?: import("./theme").FrontendTemplate
}
