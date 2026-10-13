import { apiFetch } from '../../api'
import type { CharacterPayload, Entry, LinkChoice, WorldContext } from '../../data/lifepath'

export type NarrativeResult = { narrative: string; source: 'model' | 'template'; issues: string[] }

export type FieldChange = { field: string; before: unknown; after: unknown }

export type ApplyMode = 'add' | 'overwrite' | 'campaign'

async function json<T>(path: string, init?: RequestInit): Promise<T | null> {
  try {
    const res = await apiFetch(path, init)
    if (!res.ok) return null
    return (await res.json()) as T
  } catch {
    return null
  }
}

export const draftNarrative = (req: {
  kind: 'world' | 'character'
  name: string
  entries: Entry[]
  freeform: string
  link: LinkChoice | null
  context: WorldContext
}) => json<NarrativeResult>('/lifepath/narrative', { method: 'POST', body: JSON.stringify(req) })

const clientPayload = (payload: CharacterPayload) => ({ ...payload })

export const previewApply = (characterId: number, mode: 'add' | 'overwrite', payload: CharacterPayload) =>
  json<{ committed: boolean; changes: FieldChange[] }>(`/lifepath/characters/${characterId}/apply`, {
    method: 'POST',
    body: JSON.stringify({ mode, backstory: clientPayload(payload), commit: false }),
  })

export const commitApply = (characterId: number, mode: 'add' | 'overwrite', payload: CharacterPayload) =>
  json<{ committed: boolean; changes: FieldChange[] }>(`/lifepath/characters/${characterId}/apply`, {
    method: 'POST',
    body: JSON.stringify({ mode, backstory: clientPayload(payload), commit: true }),
  })

export const undoApply = (characterId: number) =>
  json<{ ok: boolean }>(`/lifepath/characters/${characterId}/undo`, { method: 'POST' })

export const keepForCampaign = (campaignId: string, characterId: number, payload: CharacterPayload) =>
  json<{ ok: boolean }>(`/lifepath/campaigns/${campaignId}/characters/${characterId}`, {
    method: 'POST',
    body: JSON.stringify(clientPayload(payload)),
  })

export type SavedWorldSummary = { id: string; name: string; preview: string; updated_at: string | null; version: number }
export type SavedWorld = SavedWorldSummary & { narrative: string; context: Record<string, unknown>; answers: Record<string, unknown> }

export const listWorlds = () => json<{ worlds: SavedWorldSummary[] }>('/worlds')
export const getWorld = (id: string) => json<{ world: SavedWorld }>(`/worlds/${id}`)
export const saveWorld = (body: { name: string; narrative: string; context: unknown; answers: unknown }, id?: string | null) =>
  json<{ world: SavedWorld }>(id ? `/worlds/${id}` : '/worlds', { method: id ? 'PUT' : 'POST', body: JSON.stringify(body) })
export const deleteWorld = (id: string) => json<{ ok: boolean }>(`/worlds/${id}`, { method: 'DELETE' })
