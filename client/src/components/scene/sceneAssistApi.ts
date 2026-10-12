import { apiFetch } from '../../api'

export type PresentPerson = { name: string; role?: string; seen?: string }

/** The player-safe orientation summary the server builds from the story text. */
export type SceneView = {
  place?: string
  time_of_day?: string
  weather?: string
  situation?: string
  present?: PresentPerson[]
  hook?: string
}

export type RoundRecap = {
  actions?: Array<{ by: string; text: string }>
  rolls?: Array<{ by: string; expression?: string; total?: number | null }>
}

export type Recap = {
  title?: string
  character?: string
  previously?: string[]
  right_now?: string
  place?: string
  present?: PresentPerson[]
  open_question?: string
  last_played_at?: string | null
}

export type RoundStatus = {
  members: Array<{ name: string; acted: boolean; actions: number; ready: boolean }>
  paused?: boolean
  avoid?: string[]
  waiting_on: string[]
  quiet: string[]
  all_ready: boolean
}

export type SafetyKind = 'pause' | 'resume' | 'skip' | 'soften'

export type Suggestion = { suggestion: string; angle?: string; source?: string }

async function json<T>(path: string, init?: RequestInit): Promise<T | null> {
  try {
    const res = await apiFetch(path, init)
    if (!res.ok) return null
    return (await res.json()) as T
  } catch {
    return null
  }
}

export const fetchSuggestion = (sessionId: string, previous: string[]) =>
  json<Suggestion>(`/sessions/${sessionId}/suggest-action`, { method: 'POST', body: JSON.stringify({ previous }) })

export const fetchNotice = (sessionId: string) =>
  json<{ notice: string }>(`/sessions/${sessionId}/notice`, { method: 'POST' })

export const fetchRecap = (sessionId: string) => json<Recap>(`/sessions/${sessionId}/recap`)

export const fetchRound = (sessionId: string) => json<RoundStatus>(`/sessions/${sessionId}/round`)

export const postSafety = (sessionId: string, kind: SafetyKind, topic = '') =>
  json<{ ok: boolean; paused: boolean; message: string }>(`/sessions/${sessionId}/table-safety`, {
    method: 'POST',
    body: JSON.stringify({ kind, topic }),
  })

/** localStorage that never throws (private windows, blocked storage, tests). */
export const store = {
  get(key: string): string | null {
    try {
      return window.localStorage.getItem(key)
    } catch {
      return null
    }
  },
  set(key: string, value: string) {
    try {
      window.localStorage.setItem(key, value)
    } catch {
      /* the preference simply is not remembered */
    }
  },
}

/** A scene is worth a "previously" recap when the player has been away for this long. */
export const AWAY_MS = 6 * 60 * 60 * 1000

export function shouldShowRecap(sessionId: string, now = Date.now()): boolean {
  const last = Number(store.get(`tt:last-seen:${sessionId}`) || 0)
  return last > 0 && now - last > AWAY_MS
}

export function markSeen(sessionId: string, now = Date.now()) {
  store.set(`tt:last-seen:${sessionId}`, String(now))
}
