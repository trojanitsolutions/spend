import { reactive } from "vue"

/** The active Frontend Template, as sent by spend/www/spend.py and spend.api.get_boot. */
export interface FrontendTemplate {
	name?: string
	app_title?: string
	app_logo?: string
	favicon?: string
	color_mode?: "Light" | "Dark" | "System"
	primary_color?: string
	sidebar_color?: string
	font_family?: "Inter" | "System" | "Arial" | "Serif" | "Mono"
	corner_style?: "Default" | "Sharp" | "Rounded"
	density?: "Comfortable" | "Compact"
	custom_css?: string
}

const FONTS: Record<string, string> = {
	System: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
	Arial: "Arial, sans-serif",
	Serif: "Georgia, 'Times New Roman', serif",
	Mono: "ui-monospace, SFMono-Regular, Menlo, monospace",
}

// frappe-ui's radius scale, `--radius-1` … `--radius-8`, in px
const RADII = [4, 5, 6, 8, 10, 12, 16, 20]
const CORNER_SCALE: Record<string, number> = { Sharp: 0.35, Rounded: 1.6 }

/** What components read: the title and logo of the active template, with Spend's own as fallback. */
export const theme = reactive({
	appTitle: "Spend",
	appLogo: window.app_logo || "",
	sidebarColor: "",
	/** the sidebar color is dark enough to need light text */
	sidebarDark: false,
})

const darkQuery = window.matchMedia("(prefers-color-scheme: dark)")
let colorMode: FrontendTemplate["color_mode"] = "Light"
darkQuery.addEventListener("change", setColorMode)

export function applyTheme(template: FrontendTemplate = {}) {
	theme.appTitle = template.app_title || "Spend"
	theme.appLogo = template.app_logo || window.app_logo || ""
	theme.sidebarColor = template.sidebar_color || ""
	theme.sidebarDark = isDark(theme.sidebarColor)
	document.title = theme.appTitle

	colorMode = template.color_mode || "Light"
	setColorMode()
	document.documentElement.classList.toggle("density-compact", template.density === "Compact")
	setStyle("spend-theme", themeCss(template))
	setStyle("spend-custom-css", template.custom_css || "")
	setFavicon(template.favicon || window.favicon)
}

function setColorMode() {
	const dark = colorMode === "Dark" || (colorMode === "System" && darkQuery.matches)
	document.documentElement.dataset.theme = dark ? "dark" : "light"
}

/** CSS variables over frappe-ui's; added after its stylesheet so they win in both color modes. */
function themeCss(template: FrontendTemplate) {
	const vars: string[] = []
	const primary = template.primary_color
	if (primary) {
		// solid buttons, checkboxes, switches and progress bars fill with gray-10, hover with 9, press with 8
		vars.push(
			`--surface-gray-10: ${primary}`,
			`--surface-gray-9: color-mix(in srgb, ${primary} 85%, white)`,
			`--surface-gray-8: color-mix(in srgb, ${primary} 70%, white)`,
		)
	}
	const scale = CORNER_SCALE[template.corner_style || ""]
	if (scale) RADII.forEach((px, i) => vars.push(`--radius-${i + 1}: ${Math.round(px * scale)}px`))

	const rules = vars.length ? [`:root, [data-theme="dark"] { ${vars.join("; ")} }`] : []
	const font = FONTS[template.font_family || ""]
	if (font) rules.push(`html, body { font-family: ${font} }`)
	return rules.join("\n")
}

/** True for a #rgb or #rrggbb color whose relative luminance is below the midpoint. */
function isDark(color: string) {
	let hex = color.trim().replace(/^#/, "")
	if (hex.length === 3) hex = [...hex].map((c) => c + c).join("")
	if (!/^[0-9a-f]{6}$/i.test(hex)) return false
	const [r, g, b] = [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
	return 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.5
}

function setStyle(id: string, css: string) {
	let style = document.getElementById(id)
	if (!css) return style?.remove()
	if (!style) {
		style = document.createElement("style")
		style.id = id
		document.head.appendChild(style)
	}
	style.textContent = css
}

function setFavicon(href?: string) {
	if (!href) return
	const link = document.querySelector<HTMLLinkElement>("link[rel='icon']") ?? document.head.appendChild(document.createElement("link"))
	link.rel = "icon"
	link.href = href
}
