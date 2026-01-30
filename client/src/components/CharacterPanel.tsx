import React, {useMemo, useRef, useState} from 'react'
import CharacterIconStrip, {CharacterSnapshot, CharacterStripKey} from './CharacterIconStrip'
import './CharacterPanel.css'

export type SceneCue = {
  id: string
  prompt: string
  roll?: {
    type?: string
    skill?: string
    reason?: string
  }
}

export type CharacterSummary = CharacterSnapshot & {
  id: string
  name: string
  level: number
  hp: { current: number; max: number; temp?: number }
  ac: number
  spellSave: number
  inventory: string[]
  spells: string[]
}

type Props = {
  roster: CharacterSummary[]
  selectedId?: string | null
  onSelect?: (id: string) => void
  sceneCues?: SceneCue[]
  npcSpotlight?: {name: string; initiative_hint?: string}[]
  onCueRoll?: (cue: SceneCue) => Promise<void>
  title?: string
  showRoster?: boolean
}

export default function CharacterPanel({
  roster,
  selectedId,
  onSelect,
  sceneCues = [],
  npcSpotlight = [],
  onCueRoll,
  title = 'Characters',
  showRoster = true,
}: Props){
  const [drawerKey, setDrawerKey] = useState<CharacterStripKey | null>(null)
  const containerRef = useRef<HTMLDivElement|null>(null)
  const [rollingCueId, setRollingCueId] = useState<string | null>(null)
  const [cueError, setCueError] = useState<string | null>(null)

  const selected = useMemo(() => {
    if(!roster.length) return undefined
    if(!selectedId) return roster[0]
    return roster.find(r => r.id === selectedId) ?? roster[0]
  }, [roster, selectedId])

  const abilities = useMemo(() => {
    const stats = selected?.stats
    if(!stats) return []
    const computeMod = (score: number) => Math.floor((score - 10) / 2)
    const formatMod = (mod: number) => (mod >= 0 ? `+${mod}` : `${mod}`)
    const str = typeof stats.str === 'number' ? stats.str : 10
    const dex = typeof stats.dex === 'number' ? stats.dex : 10
    const wis = typeof stats.wis === 'number' ? stats.wis : 10
    const rows = [
      { key: 'STR', score: str, mod: computeMod(str) },
      { key: 'DEX', score: dex, mod: computeMod(dex) },
      { key: 'WIS', score: wis, mod: computeMod(wis) },
    ]
    return rows.map(r => ({ ...r, modLabel: formatMod(r.mod) }))
  }, [selected?.stats])

  async function handleCueRoll(cue: SceneCue){
    if(!onCueRoll || !cue.roll) return
    setCueError(null)
    setRollingCueId(cue.id)
    try{
      await onCueRoll(cue)
    }catch(err:any){
      setCueError(err?.message || 'Failed to trigger roll')
    }finally{
      setRollingCueId(null)
    }
  }

  if(!roster.length){
    return (
      <div className="character-panel-root">
        <h3 className="character-panel-title">{title}</h3>
        <div className="inline-alert">
          No character selected yet. Create/select one from Manage Characters, then come back to Play.
        </div>
      </div>
    )
  }

  return (
    <div className="character-panel-root">
      <h3 className="character-panel-title">{title}</h3>
      <CharacterIconStrip
        character={selected}
        activeKey={drawerKey}
        onSelect={(key) => {
          setDrawerKey(prev => (prev === key ? null : key))
          // keep the drawer area visible when toggled
          setTimeout(() => {
            if(containerRef.current) containerRef.current.scrollTop = 0
          }, 0)
        }}
      />
      <div className="character-panel-scroll" ref={containerRef}>
        <div className={`character-panel-layout ${drawerKey ? 'character-panel-layout--drawer' : ''}`}>
          {drawerKey ? (
            <aside className="character-panel-drawer" aria-label="Character details drawer">
              <div className="character-panel-drawer-header">
                <div className="character-panel-drawer-title">
                  {drawerKey === 'abilities' ? 'Abilities' : null}
                  {drawerKey === 'features' ? 'Features' : null}
                  {drawerKey === 'inventory' ? 'Inventory' : null}
                  {drawerKey === 'journal' ? 'Journal' : null}
                  {drawerKey === 'skills' ? 'Skills' : null}
                </div>
                <button className="character-panel-drawer-close" type="button" onClick={() => setDrawerKey(null)} aria-label="Close drawer">
                  ✕
                </button>
              </div>

              <div className="character-panel-drawer-body">
                {drawerKey === 'abilities' ? (
                  <div className="character-abilities">
                    {abilities.map(row => (
                      <div key={row.key} className="character-ability-row">
                        <div className="character-ability-key">{row.key}</div>
                        <div className="character-ability-score">{row.score}</div>
                        <div className="character-ability-mod">{row.modLabel}</div>
                      </div>
                    ))}
                    {!abilities.length ? <div className="muted">No ability scores available.</div> : null}
                  </div>
                ) : null}

                {drawerKey === 'features' ? (
                  selected?.features?.length ? (
                    <ul className="character-section-ul">
                      {selected.features.map((feature) => (
                        <li key={feature}>{feature}</li>
                      ))}
                    </ul>
                  ) : (
                    <div className="muted">No features listed.</div>
                  )
                ) : null}

                {drawerKey === 'inventory' ? (
                  selected?.inventory?.length ? (
                    <ul className="character-section-ul">
                      {selected.inventory.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  ) : (
                    <div className="muted">No inventory items.</div>
                  )
                ) : null}

                {drawerKey === 'journal' ? (
                  <div>
                    <div className="muted" style={{marginBottom: 8}}>
                      {typeof selected?.journalEntries === 'number' ? `${selected.journalEntries} entries` : 'No journal data'}
                    </div>
                    <div className="muted">Journal entry contents aren’t wired up yet.</div>
                  </div>
                ) : null}

                {drawerKey === 'skills' ? (
                  <div className="character-section-list character-section-list--skills" style={{marginTop: 0}}>
                    <ul className="character-section-ul character-section-ul--skills">
                      {selected?.skills?.map(skill => (
                        <li key={skill.name} className="character-skill-item">
                          <span className="character-skill-name">{skill.name}</span>
                          <span className="character-skill-mod">
                            {skill.mod >= 0 ? '+' : ''}{skill.mod}
                          </span>
                        </li>
                      ))}
                    </ul>
                    {!selected?.skills?.length ? <div className="muted">No skills listed.</div> : null}
                  </div>
                ) : null}
              </div>
            </aside>
          ) : null}

          <div className="character-panel-main">
            {showRoster ? (
              <div className="character-roster">
                {roster.map(entry => (
                  <div key={entry.id} className={`character-card ${entry.id === selected?.id ? 'active' : ''}`}>
                    <button onClick={() => onSelect?.(entry.id)}>
                      <div className="character-name">{entry.name}</div>
                      <div className="character-meta">HP {entry.hp.current}/{entry.hp.max} • Level {entry.level}</div>
                    </button>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </div>

        {sceneCues.length > 0 && (
          <div className="character-panel-block">
            <div className="character-panel-block-title character-panel-block-title--scene">Scene Cues</div>
            <ul className="character-panel-cues">
              {sceneCues.map((cue)=>(
                <li key={cue.id} className="character-panel-cue">
                  <div className="character-panel-cue-prompt">{cue.prompt}</div>
                  {cue.roll ? (
                    <button
                      className="btn btn-quiet btn-sm"
                      type="button"
                      onClick={()=>handleCueRoll(cue)}
                      disabled={rollingCueId === cue.id}
                    >
                      {rollingCueId === cue.id ? 'Rolling…' : `Roll ${cue.roll.skill || cue.roll.type || 'd20'}`}
                    </button>
                  ) : (
                    <div className="character-panel-cue-muted">Awaiting clarification</div>
                  )}
                </li>
              ))}
            </ul>
            {cueError && <div className="character-panel-error">{cueError}</div>}
          </div>
        )}

        {npcSpotlight.length > 0 && (
          <div className="character-panel-block">
            <div className="character-panel-block-title character-panel-block-title--npc">NPC Spotlight</div>
            <ul className="character-panel-npcs">
              {npcSpotlight.map(npc => (
                <li key={npc.name}>
                  <strong>{npc.name}</strong>{npc.initiative_hint ? ` · ${npc.initiative_hint}` : ''}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}
