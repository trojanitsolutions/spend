import { api } from "@/api"

const API = "spend.training.api"

export type Mode = "Guided" | "Practice"
export type ActionType = "Click" | "Enter Value" | "Select Option" | "Observe"

export interface Step {
	title: string
	route: string
	target: string
	target_kind: "Tour Key" | "Selector" | ""
	target_label: string
	action_type: ActionType
	body: string
	hint: string
	expected_value: string
}

export interface QuizQuestion {
	question: string
	options: string[]
}

export interface Scenario {
	name: string
	title: string
	track: string
	difficulty: string
	is_active: 0 | 1
	passing_score: number
	start_route: string
	video_url: string
	description: string
	modes: Mode[]
	steps: Step[]
	quiz: QuizQuestion[]
	next_scenario: string | null
}

export interface ScenarioSummary {
	name: string
	title: string
	track: string
	description: string
	difficulty: string
	is_active: 0 | 1
	passing_score: number
	video_url: string
	modes: Mode[]
	best: { score: number; passed: boolean; last_on: string } | null
}

export interface Track {
	name: string
	title: string
	description: string
	scenarios: ScenarioSummary[]
}

export interface Home {
	is_trainer: boolean
	training_company: string | null
	tracks: Track[]
}

export interface EditableQuestion {
	question: string
	options: string
	correct_option: string
	explanation: string
}

export interface EditableScenario extends Omit<Scenario, "modes" | "quiz" | "next_scenario"> {
	allow_guided: 0 | 1
	allow_practice: 0 | 1
	seed_data: string
	quiz: EditableQuestion[]
	tracks: string[]
}

export interface QuizResult {
	score: number
	results: { correct: boolean; correct_option: string; explanation: string }[]
}

export interface TeamRow {
	user: string
	full_name: string
	scenario: string
	track: string
	attempts: number
	best_score: number
	passed: boolean
	last_on: string
}

export const getHome = () => api<Home>(`${API}.get_home`)
export const getScenario = (name: string) => api<Scenario>(`${API}.get_scenario`, { name })
export const startTraining = (scenario: string) => api<{ company: string }>(`${API}.start_training`, { scenario })
export const checkQuiz = (scenario: string, answers: string[]) =>
	api<QuizResult>(`${API}.check_quiz`, { scenario, answers })
export const saveProgress = (args: {
	scenario: string
	mode: Mode
	step_score: number
	quiz_score: number | null
	hints_used: number
	mistakes: number
	time_taken: number
}) => api<{ name: string; status: "Passed" | "Needs Practice"; score: number }>(`${API}.save_progress`, args)
export const getTeamProgress = () => api<{ rows: TeamRow[] }>(`${API}.get_team_progress`)

export const getScenarioForEdit = (name: string) => api<EditableScenario>(`${API}.get_scenario_for_edit`, { name })
export const createScenario = (track: string, title: string, start_route?: string) =>
	api<{ name: string }>(`${API}.create_scenario`, { track, title, start_route })
export const saveScenario = (name: string, values: Partial<EditableScenario>) =>
	api<EditableScenario>(`${API}.save_scenario`, { name, values })
export const resetTrainingData = () =>
	api<{ deleted: number; failed: { doctype: string; name: string; error: string }[] }>(`${API}.reset_training_data`)
