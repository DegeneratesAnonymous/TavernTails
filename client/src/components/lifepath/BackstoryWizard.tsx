/**
 * The character backstory builder, with the choice of where the result goes:
 * added to what the character already has, written over it (with undo), or kept for one campaign only.
 */
import React, { useEffect, useMemo, useState } from 'react'
import { characterPayload, characterStages, type WorldContext } from '../../data/lifepath'
import LifePathBuilder, { type LifePathResult } from './LifePathBuilder'
import {
  commitApply, keepForCampaign, previewApply, undoApply, type ApplyMode, type FieldChange,
} from './lifepathApi'

export type BackstoryCharacter = { id: number; name: string; sheet?: Record<string, any> | null }

type Props = {
  character: BackstoryCharacter
  /** When set, "this campaign only" is offered. */
  campaignId?: string | null
  world: WorldContext
  onFinished: () => void
  onCancel: () => void
}

const FIELD_LABELS: Record<string, string> = {
  backstory: 'Backstory', bonds: 'Bonds', flaws: 'Flaws', ideals: 'Ideals', personality_traits: 'Personality',
  alignment: 'Alignment', allies: 'Allies', rivals: 'Rivals', patron: 'Patron', goals: 'Goals',
  backstory_link: 'Link to the main trouble', lifepath: 'Choices',
}
const SHOWN = (c: FieldChange) => c.field !== 'lifepath'

const show = (value: unknown): string => {
  if (value == null || value === '') return '—'
  if (Array.isArray(value)) return value.map((v) => (typeof v === 'object' && v ? (v as any).text ?? JSON.stringify(v) : String(v))).join('\n') || '—'
  if (typeof value === 'object') return (value as any).name ?? JSON.stringify(value)
  return String(value)
}

function Destination({ hasBackstory, campaignId, mode, setMode, changes }: {
  hasBackstory: boolean; campaignId?: string | null; mode: ApplyMode; setMode: (m: ApplyMode) => void; changes: FieldChange[] | null
}) {
  return (
    <fieldset role="group" aria-label="Where should this go?" style={{ border: 0, padding: 0, margin: "12px 0 0" }}>
      <legend>Where should this go?</legend>
      {([
        ['add', hasBackstory ? 'Add to my character’s backstory' : 'Save to my character'],
        ...(hasBackstory ? [['overwrite', 'Replace my character’s backstory (you can undo)']] : []),
        ...(campaignId ? [['campaign', 'Keep it for this campaign only']] : []),
      ] as Array<[ApplyMode, string]>).map(([value, label]) => (
        <label key={value} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <input type="radio" name="backstory-destination" checked={mode === value} onChange={() => setMode(value)} />
          {label}
        </label>
      ))}
      {mode !== 'campaign' && changes && (
        <div className="lifepath-diff" aria-live="polite">
          <strong>What will change</strong>
          {changes.filter(SHOWN).map((c) => (
            <div className="lifepath-diff-row" key={c.field}>
              <strong>{FIELD_LABELS[c.field] ?? c.field}</strong>
              {mode === 'overwrite' && <pre>Before: {show(c.before)}</pre>}
              <pre>{mode === 'overwrite' ? 'After: ' : ''}{show(c.after)}</pre>
            </div>
          ))}
          {!changes.filter(SHOWN).length && <span>Nothing would change.</span>}
        </div>
      )}
    </fieldset>
  )
}

export default function BackstoryWizard({ character, campaignId, world, onFinished, onCancel }: Props) {
  const stages = useMemo(() => characterStages(world), [world])
  const hasBackstory = !!String(character.sheet?.backstory ?? '').trim()
  const [mode, setMode] = useState<ApplyMode>(campaignId && hasBackstory ? 'campaign' : 'add')
  const [changes, setChanges] = useState<FieldChange[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<{ mode: ApplyMode } | null>(null)
  const label = world.world_name || 'This story'
  const [latest, setLatest] = useState<LifePathResult | null>(null)

  const payloadFor = (state: LifePathResult) => characterPayload(stages, state.answers, world, state.narrative, label)

  const latestKey = latest ? JSON.stringify([latest.narrative, latest.answers]) : ''
  useEffect(() => {
    if (!latest || mode === 'campaign' || !latest.narrative.trim()) { setChanges(null); return }
    let live = true
    void previewApply(character.id, mode, payloadFor(latest)).then((r) => { if (live) setChanges(r?.changes ?? null) })
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, latestKey, character.id])

  async function finish(state: LifePathResult) {
    setBusy(true)
    setError(null)
    const payload = payloadFor(state)
    const ok = mode === 'campaign' && campaignId
      ? await keepForCampaign(campaignId, character.id, payload)
      : await commitApply(character.id, mode === 'overwrite' ? 'overwrite' : 'add', payload)
    setBusy(false)
    if (!ok) { setError('Could not save that. Please try again.'); return }
    setDone({ mode })
  }

  if (done) {
    return (
      <div className="lifepath" role="status">
        <h2>{done.mode === 'campaign' ? 'Kept for this campaign.' : 'Saved to your character.'}</h2>
        {done.mode === 'overwrite' && (
          <button className="btn btn-secondary" type="button" onClick={async () => {
            if (await undoApply(character.id)) onCancel(); else setError('Nothing to undo.')
          }}>
            Undo
          </button>
        )}
        {error && <div className="alert alert-error">{error}</div>}
        <button className="btn btn-primary" type="button" onClick={onFinished}>Continue</button>
      </div>
    )
  }

  return (
    <>
      <LifePathBuilder
        kind="character"
        title={`${character.name}’s backstory`}
        stages={stages}
        name={character.name}
        world={world}
        doneLabel="Save"
        busy={busy}
        onCancel={onCancel}
        onDone={finish}
        onChange={setLatest}
        renderFinish={() => (
          <>
            <Destination hasBackstory={hasBackstory} campaignId={campaignId} mode={mode} setMode={setMode} changes={changes} />
            {error && <div className="alert alert-error">{error}</div>}
          </>
        )}
      />
    </>
  )
}
