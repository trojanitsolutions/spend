const OPERATOR = /^(>=|<=|!=|>|<)\s*(.+)$/

/**
 * Compare a field's value with a step's Expected Value.
 * `>=2`, `<5` and `!=Draft` work, `a|b` accepts either value, and anything
 * else is a case-insensitive match.
 */
export function matches(actual: unknown, expected: string): boolean {
	const want = expected.trim()
	if (want.includes("|") && !OPERATOR.test(want)) return want.split("|").some((alt) => equals(actual, alt.trim()))
	const op = OPERATOR.exec(want)
	if (op) {
		const [, operator, rhs] = op
		if (operator === "!=") return !equals(actual, rhs)
		const a = Number(actual)
		const b = Number(rhs)
		if (Number.isNaN(a) || Number.isNaN(b)) return false
		return operator === ">=" ? a >= b : operator === "<=" ? a <= b : operator === ">" ? a > b : a < b
	}
	return equals(actual, want)
}

function equals(actual: unknown, want: string): boolean {
	if (typeof actual === "number") return actual === Number(want)
	if (typeof actual === "boolean") return String(actual) === want.toLowerCase()
	const text = String(actual ?? "").trim()
	// inputs hold text: "10.00" is the 10 the step expects
	if (text && want && !Number.isNaN(Number(text)) && !Number.isNaN(Number(want))) return Number(text) === Number(want)
	return text.toLowerCase() === want.toLowerCase()
}
