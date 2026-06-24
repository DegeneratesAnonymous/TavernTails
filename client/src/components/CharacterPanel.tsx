import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react'
import { apiFetch } from '../api'
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

export type FeatureItem = { name: string; source?: string; description?: string }

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
  classFeatures?: FeatureItem[]
  racialFeatures?: FeatureItem[]
  otherFeatures?: FeatureItem[]
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
  onSheetUpdate?: (characterId: string, patch: Record<string, any>) => void
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
  onSheetUpdate,
}: Props){
  const [sheetTab, setSheetTab] = useState<SheetTab | null>('skills')
  const containerRef = useRef<HTMLDivElement|null>(null)
  const [rollingCueId, setRollingCueId] = useState<string | null>(null)
  const [cueError, setCueError] = useState<string | null>(null)


  // Local session-time overrides (reset when character changes)
  const prevIdRef = useRef<string | undefined>(undefined)
  const [hpLocal, setHpLocal] = useState<{current: number; max: number; temp?: number} | null>(null)
  const [slotsLocal, setSlotsLocal] = useState<Record<string, {max: number; used: number; level?: number}> | null>(null)
  const [invLocal, setInvLocal] = useState<string[] | null>(null)
  // HP edit UI
  const [hpEditOpen, setHpEditOpen] = useState(false)
  const [hpAdjInput, setHpAdjInput] = useState('')
  // Add-item UI
  const [addItemInput, setAddItemInput] = useState('')
  // Expanded spell (for inline cast flow)
  const [expandedSpell, setExpandedSpell] = useState<string | null>(null)
  const [spellUpcastOptions, setSpellUpcastOptions] = useState<{spell: string; minLevel: number; options: number[]} | null>(null)
  // Upcast flow (from ✦ Cast picker — kept for weapon/top-level cast button)
  // Rest dialog
  const [restDialog, setRestDialog] = useState<'short' | 'long' | null>(null)
  const [shortRestInput, setShortRestInput] = useState('')
  // Saving indicator

  const selected = useMemo(() => {
    if(!roster.length) return undefined
    if(!selectedId) return roster[0]
    return roster.find(r => r.id === selectedId) ?? roster[0]
  }, [roster, selectedId])

  // Reset local overrides when active character changes
  useEffect(() => {
    if (selected?.id !== prevIdRef.current) {
      setHpLocal(null)
      setSlotsLocal(null)
      setInvLocal(null)
      setHpEditOpen(false)
      setHpAdjInput('')
      setExpandedSpell(null)
      setSpellUpcastOptions(null)
      setRestDialog(null)
      setShortRestInput('')
      prevIdRef.current = selected?.id
    }
  }, [selected?.id])

  const effectiveHp = hpLocal ?? selected?.hp ?? { current: 0, max: 0 }
  const effectiveSlots: Record<string, {max: number; used: number; level?: number}> = useMemo(
    () => slotsLocal ?? (selected?.spellSlots ?? {}),
    [slotsLocal, selected?.spellSlots]
  )
  const effectiveInv: string[] = invLocal ?? (selected?.inventory ?? [])

  const pushSheetPatch = useCallback((patch: Record<string, any>) => {
    if (!selected?.id) return
    apiFetch(`/characters/${selected.id}`, {
      method: 'PUT',
      body: JSON.stringify({ sheet_patch: patch }),
    }).then(() => {
      onSheetUpdate?.(selected.id, patch)
    }).catch(() => {})
  }, [selected?.id, onSheetUpdate])

  const applyHp = useCallback((next: {current: number; max: number; temp?: number}) => {
    const clamped = { ...next, current: Math.max(0, Math.min(next.max, next.current)) }
    setHpLocal(clamped)
    pushSheetPatch({ hp: clamped })
  }, [pushSheetPatch])

  const applySlots = useCallback((next: Record<string, {max: number; used: number; level?: number}>) => {
    setSlotsLocal(next)
    pushSheetPatch({ spell_slots: next })
  }, [pushSheetPatch])

  const markSlotUsed = useCallback((lvl: string) => {
    const slot = effectiveSlots[lvl]
    if (!slot || slot.used >= slot.max) return
    applySlots({ ...effectiveSlots, [lvl]: { ...slot, used: slot.used + 1 } })
  }, [effectiveSlots, applySlots])

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

  const slotEntries = Object.entries(effectiveSlots)
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
    const hp = effectiveHp
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
            <button
              type="button"
              className="cs-hp-display"
              style={{ color: hpColor }}
              onClick={() => { setHpEditOpen(v => !v); setHpAdjInput('') }}
              title="Click to adjust HP"
            >
              {hp.current}<span className="cs-vital-denom">/{hp.max}</span>
              {hp.temp ? <span className="cs-vital-temp">+{hp.temp}</span> : null}
              <span className="cs-hp-edit-icon">✎</span>
            </button>
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

        {/* HP edit row (toggle via ✎ click) */}
        {hpEditOpen ? (
          <div className="cs-hp-edit-row">
            <div className="cs-hp-edit-group">
              <span className="cs-hp-edit-label" style={{ color: '#e05252' }}>Damage</span>
              <div className="cs-hp-edit-adj">
                <input
                  className="cs-hp-edit-input"
                  type="number"
                  min={0}
                  placeholder="0"
                  value={hpAdjInput}
                  onChange={e => setHpAdjInput(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter') {
                      const n = parseInt(hpAdjInput, 10)
                      if (!isNaN(n) && n > 0) {
                        applyHp({ ...hp, current: hp.current - n })
                        setHpAdjInput('')
                        setHpEditOpen(false)
                      }
                    }
                  }}
                />
                <button type="button" className="cs-hp-edit-btn cs-hp-edit-btn--dmg"
                  onClick={() => {
                    const n = parseInt(hpAdjInput, 10)
                    if (!isNaN(n) && n > 0) { applyHp({ ...hp, current: hp.current - n }); setHpAdjInput(''); setHpEditOpen(false) }
                  }}>
                  Apply
                </button>
              </div>
            </div>
            <div className="cs-hp-edit-group">
              <span className="cs-hp-edit-label" style={{ color: '#4caf82' }}>Heal</span>
              <div className="cs-hp-edit-adj">
                <input
                  className="cs-hp-edit-input"
                  type="number"
                  min={0}
                  placeholder="0"
                  value={hpAdjInput}
                  onChange={e => setHpAdjInput(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter') {
                      const n = parseInt(hpAdjInput, 10)
                      if (!isNaN(n) && n > 0) {
                        applyHp({ ...hp, current: hp.current + n })
                        setHpAdjInput('')
                        setHpEditOpen(false)
                      }
                    }
                  }}
                />
                <button type="button" className="cs-hp-edit-btn cs-hp-edit-btn--heal"
                  onClick={() => {
                    const n = parseInt(hpAdjInput, 10)
                    if (!isNaN(n) && n > 0) { applyHp({ ...hp, current: hp.current + n }); setHpAdjInput(''); setHpEditOpen(false) }
                  }}>
                  Apply
                </button>
              </div>
            </div>
            <button type="button" className="cs-hp-edit-close" onClick={() => setHpEditOpen(false)}>✕</button>
          </div>
        ) : null}

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
                  {Array.from({length: slot.max}).map((_,i) => {
                    const isUsed = i < slot.used
                    return (
                      <button
                        key={i}
                        type="button"
                        className={`cs-slot-pip cs-slot-pip--btn ${isUsed ? 'cs-slot-pip--used' : ''}`}
                        title={isUsed ? 'Mark slot available' : 'Mark slot used'}
                        onClick={() => {
                          const newUsed = isUsed ? i : i + 1
                          applySlots({ ...effectiveSlots, [lvl]: { ...slot, used: newUsed } })
                        }}
                      />
                    )
                  })}
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
        <div className="cs-actions">
          {quickActions.equippedWeapons.length > 0 ? (
            <>
              <span className="cs-actions-label">Weapons</span>
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
              </div>
            </>
          ) : null}

          {/* Rest buttons — always visible */}
          <div className="cs-rest-row">
            <button type="button" className="cs-action-btn cs-action-btn--rest"
              onClick={() => { setRestDialog('short'); setShortRestInput('') }}>
              Short Rest
            </button>
            <button type="button" className="cs-action-btn cs-action-btn--rest"
              onClick={() => setRestDialog('long')}>
              Long Rest
            </button>
          </div>
        </div>

        {/* Rest dialogs */}
        {restDialog === 'short' ? (
          <div className="cs-rest-dialog">
            <div className="cs-rest-dialog-title">Short Rest — Restore HP</div>
            <div className="cs-rest-dialog-row">
              <input
                className="cs-hp-edit-input"
                type="number"
                min={0}
                placeholder="HP to restore"
                value={shortRestInput}
                onChange={e => setShortRestInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') {
                    const n = parseInt(shortRestInput, 10)
                    if (!isNaN(n) && n >= 0) { applyHp({ ...hp, current: hp.current + n }); setRestDialog(null) }
                  }
                  if (e.key === 'Escape') setRestDialog(null)
                }}
                autoFocus
              />
              <button type="button" className="cs-hp-edit-btn cs-hp-edit-btn--heal"
                onClick={() => {
                  const n = parseInt(shortRestInput, 10)
                  if (!isNaN(n) && n >= 0) { applyHp({ ...hp, current: hp.current + n }); setRestDialog(null) }
                }}>
                Rest
              </button>
              <button type="button" className="cs-hp-edit-close" onClick={() => setRestDialog(null)}>✕</button>
            </div>
          </div>
        ) : null}
        {restDialog === 'long' ? (
          <div className="cs-rest-dialog">
            <div className="cs-rest-dialog-title">Long Rest</div>
            <div style={{ fontSize: 11, opacity: 0.7, marginBottom: 8 }}>
              Restore to full HP and recover all spell slots?
            </div>
            <div className="cs-rest-dialog-row">
              <button type="button" className="cs-hp-edit-btn cs-hp-edit-btn--heal"
                onClick={() => {
                  const fullHp = { ...hp, current: hp.max }
                  setHpLocal(fullHp)
                  const resetSlots = Object.fromEntries(
                    Object.entries(effectiveSlots).map(([k, s]) => [k, { ...s, used: 0 }])
                  )
                  setSlotsLocal(resetSlots)
                  pushSheetPatch({ hp: fullHp, spell_slots: resetSlots })
                  onQuickAction?.({ type: 'long_rest' })
                  setRestDialog(null)
                }}>
                Take Long Rest
              </button>
              <button type="button" className="cs-hp-edit-close" onClick={() => setRestDialog(null)}>✕</button>
            </div>
          </div>
        ) : null}

        {/* ── Tab navigation ── */}
        <div className="cs-tabs" role="tablist">
          {(['skills', 'spells', 'features', 'inventory'] as SheetTab[]).map(tab => {
            const counts: Record<SheetTab, number> = {
              skills: selected?.skills?.length ?? 0,
              spells: selected?.spells?.length ?? 0,
              features: (selected?.classFeatures?.length ?? 0) + (selected?.racialFeatures?.length ?? 0) + (selected?.otherFeatures?.length ?? 0) || (selected?.features?.length ?? 0),
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

            {sheetTab === 'spells' ? (() => {
              // Build grouped spellbook from spellbook entries (rich) or flat spells (fallback)
              const book = Array.isArray(selected?.spellbook) ? selected!.spellbook : []
              const ORDINAL: Record<string, number> = {
                cantrip: 0, cantrips: 0,
                '1st': 1, '2nd': 2, '3rd': 3, '4th': 4, '5th': 5,
                '6th': 6, '7th': 7, '8th': 8, '9th': 9,
              }
              const parseLevelFromHeader = (h: string): number => {
                const lc = h.toLowerCase()
                const m = lc.match(/(\d+)(?:st|nd|rd|th)?\s*level/)
                if (m) return Number(m[1])
                if (lc.includes('cantrip')) return 0
                const w = lc.split(/\s+/)[0]
                return ORDINAL[w] ?? 99
              }

              type SpellEntry = { name: string; level: number; save_hit?: string; time?: string; range?: string; components?: string; duration?: string; notes?: string; prepared?: boolean }
              let entries: SpellEntry[] = []

              if (book.length > 0) {
                let currentLevel = 1
                for (const e of book) {
                  if (!e) continue
                  if (e.header) currentLevel = parseLevelFromHeader(String(e.header))
                  if (!e.name) continue
                  entries.push({
                    name: String(e.name),
                    level: currentLevel,
                    save_hit: e.save_hit ? String(e.save_hit) : undefined,
                    time: e.time ? String(e.time) : undefined,
                    range: e.range ? String(e.range) : undefined,
                    components: e.components ? String(e.components) : undefined,
                    duration: e.duration ? String(e.duration) : undefined,
                    notes: e.notes ? String(e.notes) : undefined,
                    prepared: Boolean(e.prepared),
                  })
                }
              } else {
                entries = (selected?.spells ?? []).map(name => ({ name, level: 1 }))
              }

              if (!entries.length) return <div className="cs-empty">No spells recorded</div>

              // Group by level
              const grouped = new Map<number, SpellEntry[]>()
              for (const e of entries) {
                if (!grouped.has(e.level)) grouped.set(e.level, [])
                grouped.get(e.level)!.push(e)
              }
              const levels = Array.from(grouped.keys()).sort((a, b) => a - b)

              const levelLabel = (n: number) => {
                if (n === 0) return 'Cantrips'
                const ord = ['', '1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th', '9th'][n] ?? `${n}th`
                return `${ord} Level`
              }

              const handleCastFromDetail = (spell: SpellEntry) => {
                const minLevel = spell.level
                if (minLevel === 0) {
                  onQuickAction?.({ type: 'cast', detail: spell.name })
                  setExpandedSpell(null)
                  return
                }
                const available = Object.entries(effectiveSlots)
                  .filter(([lvl, s]) => {
                    const n = lvl === 'pact' ? (s.level ?? 0) : Number(lvl)
                    return n >= minLevel && s.used < s.max
                  })
                  .map(([lvl, s]) => lvl === 'pact' ? (s.level ?? 0) : Number(lvl))
                  .filter(n => n > 0)
                  .sort((a, b) => a - b)

                if (!available.length) {
                  onQuickAction?.({ type: 'cast', detail: spell.name })
                  setExpandedSpell(null)
                  return
                }
                if (available.length === 1) {
                  markSlotUsed(String(available[0]))
                  onQuickAction?.({ type: 'cast', detail: spell.name })
                  setExpandedSpell(null)
                  return
                }
                setSpellUpcastOptions({ spell: spell.name, minLevel, options: available })
              }

              return (
                <div className="cs-spell-book">
                  {levels.map(lvl => {
                    const spellsAtLevel = grouped.get(lvl)!
                    // Find slot info for this level
                    const slotKey = String(lvl)
                    const slot = lvl > 0 ? (effectiveSlots[slotKey] ?? null) : null
                    const slotsAvail = slot ? slot.max - slot.used : null

                    return (
                      <div key={lvl} className="cs-spell-level-group">
                        <div className="cs-spell-level-header">
                          <span className="cs-spell-level-label">{levelLabel(lvl)}</span>
                          {slot && slot.max > 0 ? (
                            <span className="cs-spell-level-slots">
                              {slotsAvail}/{slot.max} slots
                            </span>
                          ) : null}
                        </div>
                        {spellsAtLevel.map(spell => {
                          const isExpanded = expandedSpell === spell.name
                          const isUpcastTarget = spellUpcastOptions?.spell === spell.name
                          return (
                            <div key={spell.name} className={`cs-spell-item ${isExpanded ? 'cs-spell-item--open' : ''}`}>
                              <button
                                type="button"
                                className="cs-spell-name-btn"
                                onClick={() => {
                                  setExpandedSpell(prev => prev === spell.name ? null : spell.name)
                                  setSpellUpcastOptions(null)
                                }}
                              >
                                <span className="cs-spell-name">{spell.name}</span>
                                {spell.prepared ? <span className="cs-spell-prepared" title="Prepared">◆</span> : null}
                                {spell.save_hit ? <span className="cs-spell-tag">{spell.save_hit}</span> : null}
                                <span className="cs-spell-chevron">{isExpanded ? '▲' : '▼'}</span>
                              </button>

                              {isExpanded ? (
                                <div className="cs-spell-detail">
                                  <div className="cs-spell-meta-row">
                                    {spell.time ? <span className="cs-spell-meta"><span className="cs-spell-meta-key">Cast</span> {spell.time}</span> : null}
                                    {spell.range ? <span className="cs-spell-meta"><span className="cs-spell-meta-key">Range</span> {spell.range}</span> : null}
                                    {spell.duration ? <span className="cs-spell-meta"><span className="cs-spell-meta-key">Dur</span> {spell.duration}</span> : null}
                                    {spell.components ? <span className="cs-spell-meta"><span className="cs-spell-meta-key">Comp</span> {spell.components}</span> : null}
                                  </div>
                                  {spell.notes ? <div className="cs-spell-notes">{spell.notes}</div> : null}

                                  {isUpcastTarget ? (
                                    <div className="cs-spell-upcast">
                                      <div className="cs-spell-upcast-label">Cast at level:</div>
                                      <div className="cs-spell-upcast-options">
                                        {spellUpcastOptions!.options.map(lvlOpt => (
                                          <button
                                            key={lvlOpt}
                                            type="button"
                                            className="cs-spell-upcast-btn"
                                            onClick={() => {
                                              markSlotUsed(String(lvlOpt))
                                              onQuickAction?.({ type: 'cast', detail: spell.name })
                                              setSpellUpcastOptions(null)
                                              setExpandedSpell(null)
                                            }}
                                          >
                                            {lvlOpt === spellUpcastOptions!.minLevel ? `Level ${lvlOpt}` : `Level ${lvlOpt} ↑`}
                                          </button>
                                        ))}
                                        <button
                                          type="button"
                                          className="cs-spell-upcast-btn cs-spell-upcast-btn--cancel"
                                          onClick={() => setSpellUpcastOptions(null)}
                                        >
                                          Cancel
                                        </button>
                                      </div>
                                    </div>
                                  ) : (
                                    <button
                                      type="button"
                                      className="cs-spell-cast-btn"
                                      onClick={() => handleCastFromDetail(spell)}
                                    >
                                      {spell.level === 0 ? '✦ Cast Cantrip' : slotsAvail === 0 ? '✦ Cast (no slots)' : '✦ Cast'}
                                    </button>
                                  )}
                                </div>
                              ) : null}
                            </div>
                          )
                        })}
                      </div>
                    )
                  })}
                </div>
              )
            })() : null}

            {sheetTab === 'features' ? (() => {
              const cf = selected?.classFeatures ?? []
              const rf = selected?.racialFeatures ?? []
              const of_ = selected?.otherFeatures ?? []
              const hasGroups = cf.length > 0 || rf.length > 0 || of_.length > 0
              // Fallback: use flat features array if no categorized data
              const fallback = hasGroups ? [] : (selected?.features ?? []).map((f: any) => featureSource(f) ? { name: featureName(f), source: featureSource(f) ?? undefined, description: featureDesc(f) ?? undefined } : { name: featureName(f) })
              const groups: Array<{ label: string; items: FeatureItem[] }> = hasGroups
                ? [
                    ...(cf.length ? [{ label: 'Class Features', items: cf }] : []),
                    ...(rf.length ? [{ label: 'Racial / Species Features', items: rf }] : []),
                    ...(of_.length ? [{ label: 'Other Features', items: of_ }] : []),
                  ]
                : (fallback.length ? [{ label: 'Features', items: fallback }] : [])

              if (!groups.length) return <div className="cs-empty">No features recorded</div>

              const renderItem = (f: FeatureItem, idx: number) => (
                <div key={`${f.name}-${idx}`} className="cs-feature-item">
                  <div className="cs-feature-name">
                    {f.name}
                    {f.source ? <SourceRef source={f.source} style={{ marginLeft: 6, color: 'var(--accent, #c8941a)', fontSize: 10 }} /> : null}
                  </div>
                  {f.description ? <div className="cs-feature-desc">{f.description}</div> : null}
                </div>
              )

              return (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {groups.map(group => (
                    <div key={group.label}>
                      {groups.length > 1 ? (
                        <div style={{ fontSize: 9, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--accent, #c8941a)', opacity: 0.8, marginBottom: 4, paddingBottom: 3, borderBottom: '1px solid rgba(200,148,26,0.2)' }}>
                          {group.label}
                        </div>
                      ) : null}
                      <div className="cs-feature-list">
                        {group.items.map(renderItem)}
                      </div>
                    </div>
                  ))}
                </div>
              )
            })() : null}

            {sheetTab === 'inventory' ? (
              <div className="cs-inv-wrapper">
                {effectiveInv.length === 0 ? (
                  <div className="cs-empty">No items recorded</div>
                ) : (
                  <ul className="cs-inv-list">
                    {effectiveInv.map((item, idx) => (
                      <li key={`${item}-${idx}`} className="cs-inv-item">
                        <span className="cs-inv-name">{item}</span>
                        <button
                          type="button"
                          className="cs-inv-remove"
                          title="Remove item"
                          onClick={() => {
                            const next = effectiveInv.filter((_, i) => i !== idx)
                            setInvLocal(next)
                            pushSheetPatch({ inventory: next })
                          }}
                        >
                          ×
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                <div className="cs-inv-add">
                  <input
                    className="cs-inv-add-input"
                    type="text"
                    placeholder="Add item…"
                    value={addItemInput}
                    onChange={e => setAddItemInput(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') {
                        const val = addItemInput.trim()
                        if (!val) return
                        const next = [...effectiveInv, val]
                        setInvLocal(next)
                        pushSheetPatch({ inventory: next })
                        setAddItemInput('')
                      }
                    }}
                  />
                  <button
                    type="button"
                    className="cs-inv-add-btn"
                    disabled={!addItemInput.trim()}
                    onClick={() => {
                      const val = addItemInput.trim()
                      if (!val) return
                      const next = [...effectiveInv, val]
                      setInvLocal(next)
                      pushSheetPatch({ inventory: next })
                      setAddItemInput('')
                    }}
                  >
                    +
                  </button>
                </div>
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
