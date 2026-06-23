import React, {useMemo, useRef, useState} from 'react'
import {CharacterSnapshot} from './CharacterIconStrip'
import EmptyState from './ui/EmptyState'
import SourceRef from './ui/SourceRef'
import './CharacterPanel.css'

const WEAPON_KEYWORDS = /sword|axe|bow|dagger|mace|hammer|spear|lance|staff|wand|blade|club|flail|glaive|halberd|maul|pike|rapier|scimitar|shortsword|longbow|crossbow|trident|whip|handaxe|greataxe|battleaxe|greatsword|longsword/i

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
  class_name?: string | null
  hp: { current: number; max: number; temp?: number }
  ac: number
  spellSave: number
  inventory: string[]
  spells: string[]
  spellbook?: Array<any>
  exhaustion?: number
  deathSaves?: { successes: number; failures: number }
  spellSlots?: Record<string, { max: number; used: number; level?: number }>
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
  onQuickAction?: (action: {type: 'attack' | 'cast' | 'short_rest' | 'long_rest'; detail?: string}) => void
}

type SheetTab = 'skills' | 'spells' | 'features' | 'inventory'

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
  const [drawerKey, setDrawerKey] = useState<string | null>(null)
  const [sheetTab, setSheetTab] = useState<SheetTab | null>('skills')
  const containerRef = useRef<HTMLDivElement|null>(null)
  const [rollingCueId, setRollingCueId] = useState<string | null>(null)
  const [cueError, setCueError] = useState<string | null>(null)
  const [castPickOpen, setCastPickOpen] = useState(false)

  const selected = useMemo(() => {
    if(!roster.length) return undefined
    if(!selectedId) return roster[0]
    return roster.find(r => r.id === selectedId) ?? roster[0]
  }, [roster, selectedId])

  const computeMod = (score: number) => Math.floor((score - 10) / 2)
  const fmtMod = (mod: number) => (mod >= 0 ? `+${mod}` : `${mod}`)

  const abilities = useMemo(() => {
    const stats = selected?.stats
    if(!stats) return []
    const str = typeof stats.str === 'number' ? stats.str : 10
    const dex = typeof stats.dex === 'number' ? stats.dex : 10
    const con = typeof (stats as any).con === 'number' ? (stats as any).con : 10
    const int = typeof (stats as any).int === 'number' ? (stats as any).int : 10
    const wis = typeof stats.wis === 'number' ? stats.wis : 10
    const cha = typeof (stats as any).cha === 'number' ? (stats as any).cha : 10
    return [
      { key: 'STR', score: str, mod: computeMod(str) },
      { key: 'DEX', score: dex, mod: computeMod(dex) },
      { key: 'CON', score: con, mod: computeMod(con) },
      { key: 'INT', score: int, mod: computeMod(int) },
      { key: 'WIS', score: wis, mod: computeMod(wis) },
      { key: 'CHA', score: cha, mod: computeMod(cha) },
    ].map(r => ({ ...r, modLabel: fmtMod(r.mod) }))
  }, [selected?.stats])

  const dexMod = abilities.find(r => r.key === 'DEX')?.mod ?? 0

  const quickActions = useMemo(() => {
    const equippedWeapons = (selected?.inventory || []).filter(name => WEAPON_KEYWORDS.test(name))
    const hasSpells = (selected?.spells?.length ?? 0) > 0
    return { equippedWeapons, hasSpells }
  }, [selected?.inventory, selected?.spells])

  const spellSlots = selected?.spellSlots ?? {}
  const slotEntries = Object.entries(spellSlots)
    .filter(([, slot]) => slot.max > 0)
    .sort(([a],[b]) => a === 'pact' ? 1 : b === 'pact' ? -1 : Number(a) - Number(b))

  async function handleCueRoll(cue: SceneCue){
    if(!onCueRoll || !cue.roll) return
    setCueError(null)
    setRollingCueId(cue.id)
    try{ await onCueRoll(cue) }
    catch(err:any){ setCueError(err?.message || 'Failed to trigger roll') }
    finally{ setRollingCueId(null) }
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
                <button className="btn" type="button" onClick={onGoToCharacters}>Manage Characters</button>
              ) : null}
              {onGoToImport ? (
                <button className="btn btn-secondary" type="button" onClick={onGoToImport}>Import Character</button>
              ) : null}
            </div>
          ) : null}
        />
      </div>
    )
  }

  // ── In-session character sheet ─────────────────────────────────────────────
  if(!showRoster){
    const hp = selected?.hp ?? { current: 0, max: 0 }
    const hpPct = hp.max > 0 ? Math.max(0, Math.min(1, hp.current / hp.max)) : 0
    const hpColor = hpPct > 0.6 ? '#4caf82' : hpPct > 0.3 ? '#e0a352' : '#e05252'
    const exhaustion = selected?.exhaustion ?? 0
    const deathSaves = selected?.deathSaves ?? { successes: 0, failures: 0 }
    const showDeathSaves = hp.current <= 0
    const showExhaustion = exhaustion > 0

    const subtitle = [
      `Lv${selected?.level ?? 0}`,
      selected?.class_name ?? null,
    ].filter(Boolean).join(' ')

    const featureName = (f: any): string => {
      if(typeof f === 'string') return f
      if(f && typeof f === 'object') return String(f.name || '').trim()
      return String(f || '')
    }
    const featureSource = (f: any): string | null => {
      if(f && typeof f === 'object') return String(f.source || '').trim() || null
      return null
    }
    const featureDesc = (f: any): string | null => {
      if(f && typeof f === 'object') return String(f.description || '').trim() || null
      return null
    }

    return (
      <div className="cs-root">

        {/* ── Header ── */}
        <header className="cs-header">
          <div className="cs-portrait" aria-hidden="true">
            {(selected?.name || '?').slice(0, 1).toUpperCase()}
          </div>
          <div className="cs-identity">
            <div className="cs-name">{selected?.name ?? 'Character'}</div>
            <div className="cs-subtitle">{subtitle}</div>
          </div>
        </header>

        {/* ── Combat vitals ── */}
        <div className="cs-vitals">
          <div className="cs-vital cs-vital--hp">
            <span className="cs-vital-label">HP</span>
            <span className="cs-vital-value" style={{ color: hpColor }}>
              {hp.current}<span className="cs-vital-denom">/{hp.max}</span>
            </span>
            {hp.temp ? <span className="cs-vital-temp">+{hp.temp}</span> : null}
          </div>
          <div className="cs-vital">
            <span className="cs-vital-label">AC</span>
            <span className="cs-vital-value">{selected?.ac ?? '—'}</span>
          </div>
          <div className="cs-vital">
            <span className="cs-vital-label">Init</span>
            <span className="cs-vital-value">{dexMod >= 0 ? '+' : ''}{dexMod}</span>
          </div>
          {(selected?.spellSave ?? 0) > 0 ? (
            <div className="cs-vital">
              <span className="cs-vital-label">DC</span>
              <span className="cs-vital-value">{selected!.spellSave}</span>
            </div>
          ) : null}
        </div>

        {/* HP bar */}
        <div className="cs-hp-bar-track">
          <div className="cs-hp-bar-fill" style={{ width: `${hpPct * 100}%`, background: hpColor }} />
        </div>

        {/* Status indicators (exhaustion / death saves — only when relevant) */}
        {(showDeathSaves || showExhaustion) ? (
          <div className="cs-status-row">
            {showExhaustion ? (
              <div className="cs-status-badge cs-status-badge--warn">
                Exhaustion {exhaustion}/6
              </div>
            ) : null}
            {showDeathSaves ? (
              <div className="cs-status-badge cs-status-badge--danger">
                <span>
                  {Array.from({length: 3}).map((_,i) => (
                    <span key={i} className={`cs-ds-pip ${i < deathSaves.successes ? 'cs-ds-pip--success' : ''}`} />
                  ))}
                </span>
                <span className="cs-ds-sep">·</span>
                <span>
                  {Array.from({length: 3}).map((_,i) => (
                    <span key={i} className={`cs-ds-pip ${i < deathSaves.failures ? 'cs-ds-pip--failure' : ''}`} />
                  ))}
                </span>
              </div>
            ) : null}
          </div>
        ) : null}

        {/* ── Spell slots (always visible for casters) ── */}
        {slotEntries.length > 0 ? (
          <div className="cs-slots">
            {slotEntries.map(([lvl, slot]) => (
              <div key={lvl} className="cs-slot-row">
                <span className="cs-slot-label">{lvl === 'pact' ? 'Pact' : `L${lvl}`}</span>
                <span className="cs-slot-pips">
                  {Array.from({length: slot.max}).map((_,i) => (
                    <span key={i} className={`cs-slot-pip ${i < slot.used ? 'cs-slot-pip--used' : ''}`} />
                  ))}
                </span>
                <span className="cs-slot-count">{slot.max - slot.used}/{slot.max}</span>
              </div>
            ))}
          </div>
        ) : null}

        {/* ── Ability scores (always visible) ── */}
        <div className="cs-abilities">
          {abilities.map(row => (
            <div key={row.key} className="cs-ability">
              <span className="cs-ability-key">{row.key}</span>
              <span className="cs-ability-mod">{row.modLabel}</span>
              <span className="cs-ability-score">{row.score}</span>
            </div>
          ))}
          {!abilities.length ? (
            <div style={{gridColumn:'1/-1', fontSize:12, opacity:.5}}>No ability scores available</div>
          ) : null}
        </div>

        {/* ── Quick Actions ── */}
        {(quickActions.equippedWeapons.length > 0 || quickActions.hasSpells) ? (
          <div className="cs-actions">
            <span className="cs-actions-label">Actions</span>
            <div className="cs-actions-row">
              {quickActions.equippedWeapons.map(weapon => (
                <button
                  key={weapon}
                  type="button"
                  className="cs-action-btn cs-action-btn--attack"
                  onClick={() => onQuickAction?.({ type: 'attack', detail: weapon })}
                  title={`Attack with ${weapon}`}
                >
                  ⚔ {weapon}
                </button>
              ))}
              {quickActions.hasSpells ? (
                <div style={{ position: 'relative' }}>
                  <button
                    type="button"
                    className="cs-action-btn cs-action-btn--cast"
                    onClick={() => setCastPickOpen(v => !v)}
                  >
                    ✦ Cast
                  </button>
                  {castPickOpen ? (
                    <div className="cs-cast-picker">
                      {(selected?.spells || []).map(spell => (
                        <button
                          key={spell}
                          type="button"
                          className="cs-cast-item"
                          onClick={() => { onQuickAction?.({ type: 'cast', detail: spell }); setCastPickOpen(false) }}
                        >
                          {spell}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}
              <button type="button" className="cs-action-btn cs-action-btn--rest"
                onClick={() => onQuickAction?.({ type: 'short_rest' })}>Short Rest</button>
              <button type="button" className="cs-action-btn cs-action-btn--rest"
                onClick={() => onQuickAction?.({ type: 'long_rest' })}>Long Rest</button>
            </div>
          </div>
        ) : null}

        {/* ── Tab navigation ── */}
        <div className="cs-tabs" role="tablist">
          {(['skills', 'spells', 'features', 'inventory'] as SheetTab[]).map(tab => {
            const counts: Record<SheetTab, number> = {
              skills: selected?.skills?.length ?? 0,
              spells: selected?.spells?.length ?? 0,
              features: selected?.features?.length ?? 0,
              inventory: selected?.inventory?.length ?? 0,
            }
            return (
              <button
                key={tab}
                type="button"
                role="tab"
                aria-selected={sheetTab === tab}
                className={`cs-tab ${sheetTab === tab ? 'cs-tab--active' : ''}`}
                onClick={() => setSheetTab(prev => prev === tab ? null : tab)}
              >
                {tab.charAt(0).toUpperCase() + tab.slice(1)}
                {counts[tab] > 0 ? <span className="cs-tab-count">{counts[tab]}</span> : null}
              </button>
            )
          })}
        </div>

        {/* ── Tab content ── */}
        {sheetTab ? (
          <div className="cs-tab-body" ref={containerRef}>

            {sheetTab === 'skills' ? (
              <div className="cs-skill-list">
                {(selected?.skills || []).length === 0 ? (
                  <div className="cs-empty">No skills recorded</div>
                ) : (
                  (selected?.skills || []).map(s => (
                    <div key={s.name} className="cs-skill-item">
                      <span className="cs-skill-name">{s.name}</span>
                      <span className="cs-skill-mod">{s.mod >= 0 ? '+' : ''}{s.mod}</span>
                    </div>
                  ))
                )}
              </div>
            ) : null}

            {sheetTab === 'spells' ? (
              <div>
                {(selected?.spells || []).length === 0 ? (
                  <div className="cs-empty">No spells recorded</div>
                ) : (
                  <ul className="cs-list">
                    {(selected?.spells || []).map(spell => (
                      <li key={spell}>{spell}</li>
                    ))}
                  </ul>
                )}
              </div>
            ) : null}

            {sheetTab === 'features' ? (
              <div>
                {(selected?.features || []).length === 0 ? (
                  <div className="cs-empty">No features recorded</div>
                ) : (
                  <div className="cs-feature-list">
                    {(selected?.features || []).map((f, idx) => {
                      const name = featureName(f)
                      const src = featureSource(f)
                      const desc = featureDesc(f)
                      return (
                        <div key={`${name}-${idx}`} className="cs-feature-item">
                          <div className="cs-feature-name">
                            {name}
                            {src ? <SourceRef source={src} style={{ marginLeft: 6, color: 'var(--accent, #c8941a)', fontSize: 11 }} /> : null}
                          </div>
                          {desc ? <div className="cs-feature-desc">{desc}</div> : null}
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            ) : null}

            {sheetTab === 'inventory' ? (
              <div>
                {(selected?.inventory || []).length === 0 ? (
                  <div className="cs-empty">No inventory recorded</div>
                ) : (
                  <ul className="cs-list">
                    {(selected?.inventory || []).map(item => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                )}
              </div>
            ) : null}

          </div>
        ) : null}

        {/* ── Scene Cues ── */}
        {sceneCues.length > 0 ? (
          <div className="cs-block">
            <div className="cs-block-title cs-block-title--scene">Scene Cues</div>
            <ul className="character-panel-cues">
              {sceneCues.map(cue => (
                <li key={cue.id} className="character-panel-cue">
                  <div className="character-panel-cue-prompt">{cue.prompt}</div>
                  {cue.roll ? (
                    <button className="btn btn-quiet btn-sm" type="button"
                      onClick={() => handleCueRoll(cue)} disabled={rollingCueId === cue.id}>
                      {rollingCueId === cue.id ? 'Rolling…' : `Roll ${cue.roll.skill || cue.roll.type || 'd20'}`}
                    </button>
                  ) : (
                    <div className="character-panel-cue-muted">Awaiting clarification</div>
                  )}
                </li>
              ))}
            </ul>
            {cueError ? <div className="character-panel-error">{cueError}</div> : null}
          </div>
        ) : null}

        {/* ── NPC Spotlight ── */}
        {npcSpotlight.length > 0 ? (
          <div className="cs-block">
            <div className="cs-block-title cs-block-title--npc">NPC Spotlight</div>
            <ul className="character-panel-npcs">
              {npcSpotlight.map(npc => (
                <li key={npc.name}>
                  <strong>{npc.name}</strong>{npc.initiative_hint ? ` · ${npc.initiative_hint}` : ''}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

      </div>
    )
  }

  // ── Roster / GM view ──────────────────────────────────────────────────────
  return (
    <div className="character-panel-root">
      <h3 className="character-panel-title">{title}</h3>
      <div className="character-panel-scroll" ref={containerRef}>
        <div className="character-roster">
          {roster.map(entry => (
            <div key={entry.id} className={`character-card ${entry.id === selected?.id ? 'active' : ''}`}>
              <button onClick={() => onSelect?.(entry.id)}>
                <div className="character-name">{entry.name}</div>
                <div className="character-meta">HP {entry.hp.current}/{entry.hp.max} · AC {entry.ac} · Level {entry.level}{entry.class_name ? ` ${entry.class_name}` : ''}</div>
              </button>
            </div>
          ))}
        </div>

        {sceneCues.length > 0 ? (
          <div className="character-panel-block">
            <div className="character-panel-block-title character-panel-block-title--scene">Scene Cues</div>
            <ul className="character-panel-cues">
              {sceneCues.map(cue => (
                <li key={cue.id} className="character-panel-cue">
                  <div className="character-panel-cue-prompt">{cue.prompt}</div>
                  {cue.roll ? (
                    <button className="btn btn-quiet btn-sm" type="button"
                      onClick={() => handleCueRoll(cue)} disabled={rollingCueId === cue.id}>
                      {rollingCueId === cue.id ? 'Rolling…' : `Roll ${cue.roll.skill || cue.roll.type || 'd20'}`}
                    </button>
                  ) : (
                    <div className="character-panel-cue-muted">Awaiting clarification</div>
                  )}
                </li>
              ))}
            </ul>
            {cueError ? <div className="character-panel-error">{cueError}</div> : null}
          </div>
        ) : null}

        {npcSpotlight.length > 0 ? (
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
        ) : null}
      </div>
    </div>
  )
}
