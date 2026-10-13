import { apiFetch } from '../../api'

export type GoalStatus = 'active' | 'done' | 'dropped'
export type Goal = { id: string; term: 'short' | 'mid' | 'long'; text: string; because: string; but: string; status: GoalStatus; note: string }
export type CharacterGoals = { character_id: number; name: string; you: boolean; goals: Goal[] }
export type GoalList = { characters: CharacterGoals[]; scenes_since_review: number; suggestions: GoalSuggestion[] }
export type GoalSuggestion = {
  character: string
  character_id: number | null
  goal_id: string
  goal: string
  status: 'progressed' | 'done' | 'blocked'
  evidence: string
  you: boolean
}

async function json<T>(path: string, init?: RequestInit): Promise<T | null> {
  try {
    const res = await apiFetch(path, init)
    return res.ok ? ((await res.json()) as T) : null
  } catch {
    return null
  }
}

export const fetchGoals = (sessionId: string) => json<GoalList>(`/sessions/${sessionId}/goals`)
export const reviewGoals = (sessionId: string) => json<{ suggestions: GoalSuggestion[]; more: boolean }>(`/sessions/${sessionId}/goals/review`, { method: 'POST' })
export const dismissSuggestion = (sessionId: string, body: { character_id: number; goal_id: string }) =>
  json<{ suggestions: GoalSuggestion[] }>(`/sessions/${sessionId}/goals/dismiss`, { method: 'POST', body: JSON.stringify(body) })
export const applyGoal = (sessionId: string, body: { character_id: number; goal_id: string; status: GoalStatus; note?: string }) =>
  json<{ goals: Goal[] }>(`/sessions/${sessionId}/goals/apply`, { method: 'POST', body: JSON.stringify(body) })
export const addGoal = (sessionId: string, body: { character_id: number; term: Goal['term']; text: string; because?: string; but?: string }) =>
  json<{ goals: Goal[] }>(`/sessions/${sessionId}/goals/add`, { method: 'POST', body: JSON.stringify(body) })
