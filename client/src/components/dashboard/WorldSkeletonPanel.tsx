/**
 * Progress of the world skeleton the server builds after a card-based campaign
 * is created. Contents appear only when the owner chose "Show me the world"
 * (or to the DM); otherwise only progress is shown, so the surprise holds.
 */

import React, { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../../api'
import { WORLD_PIECES, afterPoll, type WorldPoll, type WorldState, type WorldVisibility } from './campaignCard'

const POLL_MS = 5000

const STATUS_TEXT: Record<WorldState['status'], string> = {
  not_started: '',
  pending: 'Waiting for the storyteller…',
  running: 'The storyteller is deciding what is really going on…',
  ready: 'The world underneath is ready.',
  partial: 'Some pieces are ready. The rest will be filled in during play, or you can try again.',
  failed: 'The storyteller could not build the world this time. Play fills it in as you go, or you can try again.',
  interrupted: 'Building stopped before it finished. You can pick up where it left off.',
}

function PieceDetail({ piece, data }: { piece: string; data: any }) {
  if (!data) return null
  if (piece === 'truth') {
    return (
      <div className="world-piece-detail">
        <div><strong>{data.thread_name}</strong>: {data.hidden_truth}</div>
        <div>First clue: {data.first_clue}</div>
      </div>
    )
  }
  if (piece === 'factions' || piece === 'npcs') {
    return (
      <ul className="world-piece-detail">
        {(Array.isArray(data) ? data : []).map((item: any) => (
          <li key={item.name}>
            <strong>{item.name}</strong>{item.role ? ` (${item.role})` : ''}
            {item.wants ? ` Wants: ${item.wants}` : ''}
            {item.secret ? ` Secret: ${item.secret}` : ''}
          </li>
        ))}
      </ul>
    )
  }
  if (piece === 'clock') {
    return (
      <div className="world-piece-detail">
        <strong>{data.title}</strong> (by {data.deadline}): {(data.steps || []).join(' → ')}
      </div>
    )
  }
  return null
}

export default function WorldSkeletonPanel({ campaignId, canEdit }: { campaignId: string; canEdit: boolean }) {
  const [world, setWorld] = useState<WorldState | null>(null)
  const [busy, setBusy] = useState(false)
  // Bumped after a retry so the polling effect starts again.
  const [pollRound, setPollRound] = useState(0)

  const load = useCallback(async (): Promise<WorldPoll> => {
    try {
      const res = await apiFetch(`/campaigns/${campaignId}/world`)
      if (res.status === 403 || res.status === 404) return { kind: 'gone' }
      if (!res.ok) return { kind: 'error' }
      const body = await res.json()
      return { kind: 'ok', world: (body.world ?? null) as WorldState | null }
    } catch {
      return { kind: 'error' }
    }
  }, [campaignId])

  useEffect(() => {
    let live = true
    let timer: ReturnType<typeof setTimeout> | undefined
    let last: WorldState | null = null
    let errors = 0
    const tick = async () => {
      const outcome = afterPoll(await load(), last, errors)
      if (!live) return
      last = outcome.world
      errors = outcome.errorsInARow
      setWorld(outcome.world)
      if (outcome.again) timer = setTimeout(tick, POLL_MS)
    }
    tick()
    return () => {
      live = false
      if (timer) clearTimeout(timer)
    }
  }, [load, pollRound])

  useEffect(() => { setWorld(null) }, [campaignId])

  async function update(body: { visibility?: WorldVisibility; retry?: boolean }) {
    setBusy(true)
    try {
      const res = await apiFetch(`/campaigns/${campaignId}/world`, { method: 'POST', body: JSON.stringify(body) })
      if (res.ok) {
        setWorld((await res.json()).world as WorldState)
        if (body.retry) setPollRound((n) => n + 1)
      }
    } finally {
      setBusy(false)
    }
  }

  if (!world || world.status === 'not_started') return null
  const canRetry = canEdit && ['partial', 'failed', 'interrupted'].includes(world.status)

  return (
    <div className="card card-pad" style={{ marginTop: 12 }} aria-live="polite">
      <div className="row-wrap card-section-header" style={{ justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
        <div>The world underneath</div>
        {canEdit && world.can_change_visibility && (
          <button
            className="btn btn-quiet btn-sm"
            type="button"
            disabled={busy}
            onClick={() => update({ visibility: world.visibility === 'show' ? 'surprise' : 'show' })}
          >
            {world.visibility === 'show' ? 'Keep it a surprise' : 'Show me the world'}
          </button>
        )}
      </div>
      <p className="muted" style={{ fontSize: 13, margin: '8px 0' }}>{STATUS_TEXT[world.status]}</p>
      <ul className="world-pieces">
        {WORLD_PIECES.map(({ id, label }) => {
          const piece = world.pieces[id] ?? { status: 'pending' }
          const mark = piece.status === 'ready' ? '✓' : piece.status === 'failed' ? '–' : '…'
          return (
            <li key={id}>
              <div className={`world-piece world-piece--${piece.status}`}>
                <span className="world-piece-mark" aria-hidden="true">{mark}</span>
                <span>{label}{piece.status === 'failed' ? ' (left for play)' : ''}</span>
              </div>
              <PieceDetail piece={id} data={piece.data} />
            </li>
          )
        })}
      </ul>
      {canRetry && (
        <button className="btn btn-secondary btn-sm" type="button" style={{ marginTop: 10 }} disabled={busy} onClick={() => update({ retry: true })}>
          Try the missing pieces again
        </button>
      )}
    </div>
  )
}
