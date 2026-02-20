import React, {useMemo, useRef, useState} from 'react'
import CharacterIconStrip, {CharacterSnapshot, CharacterStripKey} from './CharacterIconStrip'
import EmptyState from './ui/EmptyState'
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
  spellbook?: Array<any>
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
  onGoToCharacters?: () => void
  onGoToImport?: () => void
  /** Called when the player uses a Quick Action in-session */
  onQuickAction?: (action: {type: 'attack' | 'cast' | 'short_rest' | 'long_rest'; detail?: string}) => void
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
  onGoToCharacters,
  onGoToImport,
  onQuickAction,
}: Props){
  const [drawerKey, setDrawerKey] = useState<CharacterStripKey | null>(null)
  const containerRef = useRef<HTMLDivElement|null>(null)
  const [rollingCueId, setRollingCueId] = useState<string | null>(null)
  const [cueError, setCueError] = useState<string | null>(null)
  const [castPickOpen, setCastPickOpen] = useState(false)

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
    const con = typeof (stats as any).con === 'number' ? (stats as any).con : 10
    const int = typeof (stats as any).int === 'number' ? (stats as any).int : 10
    const wis = typeof stats.wis === 'number' ? stats.wis : 10
    const cha = typeof (stats as any).cha === 'number' ? (stats as any).cha : 10
    const rows = [
      { key: 'STR', score: str, mod: computeMod(str) },
      { key: 'DEX', score: dex, mod: computeMod(dex) },
      { key: 'CON', score: con, mod: computeMod(con) },
      { key: 'INT', score: int, mod: computeMod(int) },
      { key: 'WIS', score: wis, mod: computeMod(wis) },
      { key: 'CHA', score: cha, mod: computeMod(cha) },
    ]
    return rows.map(r => ({ ...r, modLabel: formatMod(r.mod) }))
  }, [selected?.stats])

  const overview = useMemo(() => {
    if(!selected) return null
    const hpCurrent = typeof selected.hp?.current === 'number' ? selected.hp.current : 0
    const hpMax = typeof selected.hp?.max === 'number' ? selected.hp.max : 0
    const tempHp = typeof selected.hp?.temp === 'number' ? selected.hp.temp : 0
    const ac = typeof selected.ac === 'number' ? selected.ac : 0
    const level = typeof selected.level === 'number' ? selected.level : 0
    const spellSave = typeof selected.spellSave === 'number' ? selected.spellSave : 0

    const dexRow = abilities.find(r => r.key === 'DEX')
    const initMod = dexRow ? dexRow.mod : 0

    const inventoryCount = Array.isArray(selected.inventory) ? selected.inventory.length : 0
    const featuresCount = Array.isArray(selected.features) ? selected.features.length : 0
    const skillsCount = Array.isArray(selected.skills) ? selected.skills.length : 0

    return {
      hpCurrent,
      hpMax,
      tempHp,
      ac,
      level,
      spellSave,
      initMod,
      inventoryCount,
      featuresCount,
      skillsCount,
    }
  }, [abilities, selected])

  const drawerTitle = useMemo(() => {
    if(drawerKey === 'abilities') return 'Abilities'
    if(drawerKey === 'features') return 'Features'
    if(drawerKey === 'inventory') return 'Inventory'
    if(drawerKey === 'journal') return 'Journal'
    if(drawerKey === 'skills') return 'Skills'
    return 'Overview'
  }, [drawerKey])

  const drawerContent = useMemo(() => {
    if(drawerKey === 'abilities'){
      return (
        <div className="character-abilities character-abilities--tiles">
          {abilities.map(row => (
            <div key={row.key} className="character-ability-tile">
              <div className="character-ability-key">{row.key}</div>
              <div className="character-ability-mod">{row.modLabel}</div>
              <div className="character-ability-score">{row.score}</div>
            </div>
          ))}
          {!abilities.length ? <div className="muted">No ability scores available.</div> : null}
        </div>
      )
    }

    if(drawerKey === 'features'){
      return selected?.features?.length ? (
        <ul className="character-section-ul">
          {selected.features.map((feature) => (
            <li key={feature}>{feature}</li>
          ))}
        </ul>
      ) : (
        <div className="muted">No features listed.</div>
      )
    }

    if(drawerKey === 'inventory'){
      return selected?.inventory?.length ? (
        <ul className="character-section-ul">
          {selected.inventory.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <div className="muted">No inventory items.</div>
      )
    }

    if(drawerKey === 'journal'){
      return (
        <div>
          <div className="muted" style={{marginBottom: 8}}>
            {typeof selected?.journalEntries === 'number' ? `${selected.journalEntries} entries` : 'No journal data'}
          </div>
          <div className="muted">Journal entry contents aren’t wired up yet.</div>
        </div>
      )
    }

    if(drawerKey === 'skills'){
      return (
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
      )
    }

    return null
  }, [abilities, drawerKey, selected])

  const previewContent = useMemo(() => {
    if(!selected) return null
    const features = Array.isArray(selected.features) ? selected.features : []
    const inventory = Array.isArray(selected.inventory) ? selected.inventory : []
    const skills = Array.isArray(selected.skills) ? selected.skills : []

    const topFeatures = features.slice(0, 6)
    const topInventory = inventory.slice(0, 6)
    const topSkills = skills.slice(0, 12)

    return (
      <div className="character-sheet-preview">
        <div className="character-sheet-preview-row">
          <div className="character-sheet-preview-col">
            <div className="character-sheet-subhead">Skills</div>
            {topSkills.length ? (
              <ul className="character-sheet-mini-list">
                {topSkills.map(s => (
                  <li key={s.name}>
                    <span className="character-sheet-mini-name">{s.name}</span>
                    <span className="character-sheet-mini-mod">{s.mod >= 0 ? '+' : ''}{s.mod}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="muted">No skills listed.</div>
            )}
          </div>

          <div className="character-sheet-preview-col">
            <div className="character-sheet-subhead">Features</div>
            {topFeatures.length ? (
              <ul className="character-sheet-mini-list">
                {topFeatures.map(f => (<li key={f}>{f}</li>))}
              </ul>
            ) : (
              <div className="muted">No features listed.</div>
            )}

            <div className="character-sheet-subhead" style={{marginTop: 12}}>Inventory</div>
            {topInventory.length ? (
              <ul className="character-sheet-mini-list">
                {topInventory.map(i => (<li key={i}>{i}</li>))}
              </ul>
            ) : (
              <div className="muted">No inventory items.</div>
            )}
          </div>
        </div>
      </div>
    )
  }, [selected])

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
        <EmptyState
          title="No characters yet"
          description="Create or import a character, then return to Play."
          actions={!showRoster && (onGoToCharacters || onGoToImport) ? (
            <div style={{display: 'flex', gap: 8, justifyContent: 'center', flexWrap: 'wrap'}}>
              {onGoToCharacters ? (
                <button className="btn" type="button" onClick={onGoToCharacters}>
                  Manage Characters
                </button>
              ) : null}
              {onGoToImport ? (
                <button className="btn btn-secondary" type="button" onClick={onGoToImport}>
                  Import Character
                </button>
              ) : null}
            </div>
          ) : null}
        />
      </div>
    )
  }

  // Player-sheet mode: BG3/D&D Beyond-inspired, space-efficient layout
  if(!showRoster){
    return (
      <div className="character-panel-root character-panel-root--sheet">
        <div className="character-sheet-header">
          <div className="character-sheet-portrait" aria-hidden="true">
            <div className="character-sheet-portrait-initial">{(selected?.name || '?').slice(0, 1).toUpperCase()}</div>
          </div>
          <div className="character-sheet-title">
            <div className="character-sheet-name">{selected?.name}</div>
            <div className="character-sheet-subtitle muted">Level {selected?.level ?? 0}</div>
          </div>
        </div>

        {overview ? (
          <section className="player-status" aria-label="Player stats" style={{padding: 10, borderRadius: 12, border: '1px solid rgba(255,255,255,0.06)', marginBottom: 10}}>
            <div className="player-status-grid">
              <div>
                <div className="player-status-label">Armor Class</div>
                <div className="player-status-value">{overview.ac}</div>
              </div>
              <div>
                <div className="player-status-label">Hit Points</div>
                <div className="player-status-value">{overview.hpCurrent} / {overview.hpMax}</div>
              </div>
              <div>
                <div className="player-status-label">Temp HP</div>
                <div className="player-status-value">{overview.tempHp}</div>
              </div>
              <div>
                <div className="player-status-label">Initiative</div>
                <div className="player-status-value">{overview.initMod >= 0 ? '+' : ''}{overview.initMod}</div>
              </div>
              <div>
                <div className="player-status-label">Exhaustion</div>
                <div className="player-status-value">0</div>
              </div>
              <div>
                <div className="player-status-label">Spell Save DC</div>
                <div className="player-status-value">{overview.spellSave}</div>
              </div>
            </div>
          </section>
        ) : null}

        {/* Quick Actions — only in session mode */}
        {(() => {
          const weaponKeywords = /sword|axe|bow|dagger|mace|hammer|spear|lance|staff|wand|blade|club|flail|glaive|halberd|maul|pike|rapier|scimitar|shortsword|longbow|crossbow|trident|whip|handaxe|greataxe|battleaxe|greatsword|longsword/i
          const equippedWeapons = (selected?.inventory || []).filter(name => weaponKeywords.test(name))
          const hasSpells = (selected?.spells?.length ?? 0) > 0
          if(!equippedWeapons.length && !hasSpells) return null
          return (
            <div className="character-quick-actions" aria-label="Quick Actions">
              <div className="character-quick-actions-title">Actions</div>
              <div className="character-quick-actions-row">
                {equippedWeapons.map(weapon => (
                  <button
                    key={weapon}
                    type="button"
                    className="btn btn-sm character-quick-action-btn character-quick-action-btn--attack"
                    onClick={() => onQuickAction?.({ type: 'attack', detail: weapon })}
                    title={`Attack with ${weapon}`}
                  >
                    ⚔ {weapon}
                  </button>
                ))}
                {hasSpells ? (
                  <div style={{ position: 'relative' }}>
                    <button
                      type="button"
                      className="btn btn-sm character-quick-action-btn character-quick-action-btn--cast"
                      onClick={() => setCastPickOpen(v => !v)}
                    >
                      ✦ Cast Spell
                    </button>
                    {castPickOpen ? (
                      <div className="character-cast-picker">
                        {(selected?.spells || []).map(spell => (
                          <button
                            key={spell}
                            type="button"
                            className="character-cast-picker-item"
                            onClick={() => { onQuickAction?.({ type: 'cast', detail: spell }); setCastPickOpen(false) }}
                          >
                            {spell}
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
                <button
                  type="button"
                  className="btn btn-sm btn-quiet character-quick-action-btn"
                  onClick={() => onQuickAction?.({ type: 'short_rest' })}
                  title="Take a short rest"
                >
                  Short Rest
                </button>
                <button
                  type="button"
                  className="btn btn-sm btn-quiet character-quick-action-btn"
                  onClick={() => onQuickAction?.({ type: 'long_rest' })}
                  title="Take a long rest"
                >
                  Long Rest
                </button>
              </div>
            </div>
          )
        })()}


        <CharacterIconStrip
          character={selected}
          activeKey={drawerKey}
          variant="tabs"
          hiddenKeys={['abilities']}
          onSelect={(key) => {
            setDrawerKey(prev => (prev === key ? null : key))
            setTimeout(() => {
              if(containerRef.current) containerRef.current.scrollTop = 0
            }, 0)
          }}
        />

        <div className="character-panel-scroll" ref={containerRef}>
          <div className="character-sheet-abilities" aria-label="Ability scores">
            {abilities.map(row => (
              <button
                key={row.key}
                type="button"
                className="character-ability-tile character-ability-tile--button"
                onClick={() => setDrawerKey(prev => (prev === 'abilities' ? null : 'abilities'))}
                aria-label={`View abilities details (${row.key})`}
              >
                <div className="character-ability-key">{row.key}</div>
                <div className="character-ability-mod">{row.modLabel}</div>
                <div className="character-ability-score">{row.score}</div>
              </button>
            ))}
          </div>

          <div className="character-sheet-grid">
            <div className="character-sheet-card" aria-label="Skills">
              <div className="character-sheet-card-header">
                <div className="character-sheet-card-title">Skills</div>
                <button
                  type="button"
                  className={`character-sheet-card-action ${drawerKey === 'skills' ? 'active' : ''}`}
                  onClick={() => setDrawerKey(prev => (prev === 'skills' ? null : 'skills'))}
                >
                  {drawerKey === 'skills' ? 'Hide' : 'Show all'}
                </button>
              </div>
              {drawerKey === 'skills' ? drawerContent : (
                <div className="character-sheet-mini-skills">
                  <ul className="character-sheet-mini-list">
                    {(selected?.skills || []).slice(0, 14).map(s => (
                      <li key={s.name}>
                        <span className="character-sheet-mini-name">{s.name}</span>
                        <span className="character-sheet-mini-mod">{s.mod >= 0 ? '+' : ''}{s.mod}</span>
                      </li>
                    ))}
                  </ul>
                  {!selected?.skills?.length ? <div className="muted">No skills listed.</div> : null}
                </div>
              )}
            </div>

            <div className="character-sheet-card" aria-label="Character details">
              <div className="character-sheet-card-header">
                <div className="character-sheet-card-title">{drawerTitle}</div>
                {drawerKey ? (
                  <button
                    type="button"
                    className="character-panel-drawer-close"
                    onClick={() => setDrawerKey(null)}
                    aria-label="Close details"
                  >
                    ✕
                  </button>
                ) : null}
              </div>
              <div className="character-sheet-card-body">
                {drawerKey ? drawerContent : previewContent}
              </div>
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
                  {drawerTitle}
                </div>
                <button className="character-panel-drawer-close" type="button" onClick={() => setDrawerKey(null)} aria-label="Close drawer">
                  ✕
                </button>
              </div>

              <div className="character-panel-drawer-body">
                {drawerContent}
              </div>
            </aside>
          ) : null}

          <div className="character-panel-main">
            {!showRoster && !drawerKey && overview ? (
              <div className="character-overview">
                <div className="character-overview-header">
                  <div>
                    <div className="character-overview-name">{selected?.name}</div>
                    <div className="character-overview-subtitle muted">Tap a button above for details</div>
                  </div>

            {Array.isArray((selected as any)?.spellbook) && (selected as any).spellbook.length ? (
              <div className="character-sheet-card" aria-label="Spellbook" style={{ marginTop: 12 }}>
                <div className="character-sheet-card-header">
                  <div className="character-sheet-card-title">Spellbook</div>
                </div>
                <div style={{ maxHeight: 260, overflow: 'auto' }}>
                  <table className="spellbook-table">
                    <thead>
                      <tr>
                        <th className="spellbook-col spellbook-col--prep">Prep</th>
                        <th className="spellbook-col">Spell</th>
                        <th className="spellbook-col">Source</th>
                        <th className="spellbook-col">Save/Atk</th>
                        <th className="spellbook-col">Time</th>
                        <th className="spellbook-col">Range</th>
                        <th className="spellbook-col">Comp</th>
                        <th className="spellbook-col">Duration</th>
                        <th className="spellbook-col">Page</th>
                        <th className="spellbook-col">Notes</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(() => {
                        const rows: any[] = []
                        let lastHeader: string | null = null
                        ;(selected as any).spellbook.slice(0, 120).forEach((spell: any, idx: number) => {
                          const header = (spell?.header || spell?.slot_header || '').trim()
                          if (header && header !== lastHeader) {
                            lastHeader = header
                            rows.push({ type: 'header', label: header, key: `header-${idx}` })
                          }
                          rows.push({ type: 'spell', spell, key: `spellbook-${idx}` })
                        })
                        return rows.map((row) => {
                          if (row.type === 'header') {
                            return (
                              <tr key={row.key} className="spellbook-header-row">
                                <td colSpan={10}>{row.label}</td>
                              </tr>
                            )
                          }
                          const spell = row.spell
                          const prepared = String(spell?.prepared || '').toLowerCase()
                          const isPrepared = ['yes', 'true', '1', 'prepared', 'y'].includes(prepared) || prepared === 'o' || prepared === '○'
                          return (
                            <tr key={row.key}>
                              <td className="spellbook-prep">{isPrepared ? '●' : '○'}</td>
                              <td className="spellbook-name">{spell?.name || '—'}</td>
                              <td>{spell?.source || '—'}</td>
                              <td>{spell?.save_hit || '—'}</td>
                              <td>{spell?.time || '—'}</td>
                              <td>{spell?.range || '—'}</td>
                              <td>{spell?.components || '—'}</td>
                              <td>{spell?.duration || '—'}</td>
                              <td>{spell?.page || '—'}</td>
                              <td>{spell?.notes || '—'}</td>
                            </tr>
                          )
                        })
                      })()}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}
                </div>

                <div className="character-overview-grid">
                  <div className="character-overview-card">
                    <div className="character-overview-label">HP</div>
                    <div className="character-overview-value">
                      {overview.hpCurrent}/{overview.hpMax}
                      {overview.tempHp ? <span className="character-overview-muted"> (+{overview.tempHp} temp)</span> : null}
                    </div>
                  </div>

                  <div className="character-overview-card">
                    <div className="character-overview-label">AC</div>
                    <div className="character-overview-value">{overview.ac}</div>
                  </div>

                  <div className="character-overview-card">
                    <div className="character-overview-label">Level</div>
                    <div className="character-overview-value">{overview.level}</div>
                  </div>

                  <div className="character-overview-card">
                    <div className="character-overview-label">Initiative</div>
                    <div className="character-overview-value">
                      {overview.initMod >= 0 ? '+' : ''}{overview.initMod}
                    </div>
                  </div>

                  <div className="character-overview-card">
                    <div className="character-overview-label">Spell Save DC</div>
                    <div className="character-overview-value">{overview.spellSave}</div>
                  </div>
                </div>

                <div className="character-overview-meta">
                  <div className="character-overview-pill">Features: {overview.featuresCount}</div>
                  <div className="character-overview-pill">Inventory: {overview.inventoryCount}</div>
                  <div className="character-overview-pill">Skills: {overview.skillsCount}</div>
                </div>
              </div>
            ) : null}

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
