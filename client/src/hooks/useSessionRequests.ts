import { useCallback, useRef } from 'react'
import { apiFetch } from '../api'

// Share pending metadata reads and keep auto-created sessions until the campaign
// list catches up. Manual session creation does not use this cache.
export function useSessionRequests() {
  const metadata = useRef(new Map<string, Promise<any>>())
  const creations = useRef(new Map<string, Promise<any>>())

  const loadSessionMeta = useCallback((id: string) => {
    let pending = metadata.current.get(id)
    if (!pending) {
      pending = apiFetch(`/sessions/${id}/meta`).then(async response => {
        if (!response.ok) throw new Error('Unable to load session metadata')
        return response.json()
      }).finally(() => { metadata.current.delete(id) })
      metadata.current.set(id, pending)
    }
    return pending
  }, [])

  const ensureCampaignSession = useCallback((id: string) => {
    let pending = creations.current.get(id)
    if (!pending) {
      pending = apiFetch(`/campaigns/${id}/create_session`, { method: 'POST' })
        .then(async response => {
          if (!response.ok) throw new Error('Unable to create session')
          const data = await response.json()
          if (!data?.session_id) throw new Error('Missing session ID')
          return data
        }).catch(error => {
          creations.current.delete(id)
          throw error
        })
      creations.current.set(id, pending)
    }
    return pending
  }, [])

  const forgetCampaignSession = useCallback((id: string) => {
    creations.current.delete(id)
  }, [])

  return { loadSessionMeta, ensureCampaignSession, forgetCampaignSession }
}
