/** The world builder, with the option to keep the result in the player's library of saved worlds. */
import React, { useMemo, useState } from 'react'
import { worldStages, type Answers, type WorldContext } from '../../data/lifepath'
import LifePathBuilder, { type LifePathResult } from './LifePathBuilder'
import { saveWorld } from './lifepathApi'

export type WorldUse = { narrative: string; answers: Answers; context: WorldContext; savedId: string | null }

type Props = {
  initialAnswers?: Answers
  /** Set when editing a world from the library. */
  savedId?: string | null
  savedName?: string
  onCancel: () => void
  onUse: (world: WorldUse) => void
}

const EMPTY: WorldContext = { world_name: '', conflict: '', factions: [], places: [], tone: '', narrative: '' }

export default function WorldBuilder({ initialAnswers, savedId = null, savedName = '', onCancel, onUse }: Props) {
  const stages = useMemo(() => worldStages(), [])
  const [keep, setKeep] = useState(true)
  const [name, setName] = useState(savedName)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [latest, setLatest] = useState<LifePathResult | null>(null)

  const proposed = (latest?.world.world_name || '').trim()
  const finalName = (name || proposed || 'My world').trim()

  async function finish(state: LifePathResult) {
    setBusy(true)
    setError(null)
    let id = savedId
    if (keep) {
      const saved = await saveWorld(
        { name: finalName, narrative: state.narrative, context: { ...state.world, narrative: state.narrative }, answers: state.answers },
        savedId,
      )
      if (!saved) {
        setBusy(false)
        setError('Could not save the world to your library. You can still use it for this campaign.')
        return
      }
      id = saved.world.id
    }
    setBusy(false)
    onUse({ narrative: state.narrative, answers: state.answers, context: { ...state.world, narrative: state.narrative }, savedId: id })
  }

  return (
    <LifePathBuilder
      kind="world"
      title="Build your world"
      stages={stages}
      name={proposed}
      world={EMPTY}
      initialAnswers={initialAnswers}
      doneLabel="Use this world"
      busy={busy}
      onCancel={onCancel}
      onDone={finish}
      onChange={setLatest}
      renderFinish={() => (
        <div style={{ marginTop: 12, display: 'grid', gap: 8 }}>
          <label style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <input type="checkbox" checked={keep} onChange={(e) => setKeep(e.target.checked)} />
            {savedId ? 'Update my saved copy of this world' : 'Save this world to my library'}
          </label>
          {keep && (
            <label>
              World name in my library
              <input className="input" value={name || proposed} onChange={(e) => setName(e.target.value)} maxLength={120} />
            </label>
          )}
          {error && <div className="alert alert-error">{error}</div>}
        </div>
      )}
    />
  )
}
