import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react'
import { apiFetch } from '../api'
import {CharacterSnapshot} from './CharacterIconStrip'
import EmptyState from './ui/EmptyState'
import SourceRef from './ui/SourceRef'
import './CharacterPanel.css'

const WEAPON_KEYWORDS = /sword|axe|bow|dagger|mace|hammer|spear|lance|staff|wand|blade|club|flail|glaive|halberd|maul|pike|rapier|scimitar|shortsword|longbow|crossbow|trident|whip|handaxe|greataxe|battleaxe|greatsword|longsword/i

// Standard D&D 5e spell slot tables indexed by character level
const _FULL_CASTER_SLOTS: number[][] = [
  [],                        // 0 unused
  [2],                       // 1
  [3],                       // 2
  [4,2],                     // 3
  [4,3],                     // 4
  [4,3,2],                   // 5
  [4,3,3],                   // 6
  [4,3,3,1],                 // 7
  [4,3,3,2],                 // 8
  [4,3,3,3,1],               // 9
  [4,3,3,3,2],               // 10
  [4,3,3,3,2,1],             // 11
  [4,3,3,3,2,1],             // 12
  [4,3,3,3,2,1,1],           // 13
  [4,3,3,3,2,1,1],           // 14
  [4,3,3,3,2,1,1,1],         // 15
  [4,3,3,3,2,1,1,1],         // 16
  [4,3,3,3,2,1,1,1,1],       // 17
  [4,3,3,3,3,1,1,1,1],       // 18
  [4,3,3,3,3,2,1,1,1],       // 19
  [4,3,3,3,3,2,2,1,1],       // 20
]
const _HALF_CASTER_SLOTS: number[][] = [
  [],[],[2],[3],[3],[4,2],[4,2],[4,3],[4,3],[4,3,2],[4,3,2],
  [4,3,3],[4,3,3],[4,3,3,1],[4,3,3,1],[4,3,3,2],[4,3,3,2],
  [4,3,3,3,1],[4,3,3,3,1],[4,3,3,3,2],[4,3,3,3,2],
]
const _THIRD_CASTER_SLOTS: number[][] = [
  [],[],[],[2],[3],[3],[3],[4,2],[4,2],[4,2],[4,3],
  [4,3],[4,3],[4,3,2],[4,3,2],[4,3,2],[4,3,3],[4,3,3],
  [4,3,3],[4,3,3,1],[4,3,3,1],
]

function computeStandardSlots(
  className: string | null | undefined,
  level: number | undefined
): Record<string, {max: number; used: number}> {
  const cn = (className ?? '').toLowerCase()
  const lvl = Math.max(1, Math.min(20, level ?? 1))
  if (!cn) return {}
  let table: number[][] | null = null
  if (/wizard|cleric|druid|bard|sorcerer/.test(cn)) table = _FULL_CASTER_SLOTS
  else if (/paladin|ranger|artificer/.test(cn)) table = _HALF_CASTER_SLOTS
  else if (/eldritch knight|arcane trickster/.test(cn)) table = _THIRD_CASTER_SLOTS
  if (!table) return {}
  const slots = table[lvl] ?? []
  const result: Record<string, {max: number; used: number}> = {}
  slots.forEach((max, i) => { if (max > 0) result[String(i + 1)] = { max, used: 0 } })
  return result
}

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
  preparedOverrides?: Record<string, boolean>
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
  sessionId?: string | null
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
  sessionId,
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
  // Concentration tracking
  const [concentratingOn, setConcentratingOn] = useState<string | null>(null)
  const [concWarning, setConcWarning] = useState<{spell: string; action: () => void} | null>(null)
  // Spell filter + preparation management
  const [spellFilter, setSpellFilter] = useState<'castable' | 'all' | 'ritual'>('castable')
  const [preparedOverridesLocal, setPreparedOverridesLocal] = useState<Record<string, boolean> | null>(null)
  const [showAllKnown, setShowAllKnown] = useState(false)
  const [showAddSpell, setShowAddSpell] = useState(false)
  const [addSpellName, setAddSpellName] = useState('')
  const [addSpellLevel, setAddSpellLevel] = useState(1)
  // Rest dialog
  const [restDialog, setRestDialog] = useState<'short' | 'long' | null>(null)
  const [shortRestInput, setShortRestInput] = useState('')

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
      setConcentratingOn(null)
      setConcWarning(null)
      setSpellFilter('castable')
      setPreparedOverridesLocal(null)
      setShowAllKnown(false)
      setShowAddSpell(false)
      setAddSpellName('')
      setAddSpellLevel(1)
      setRestDialog(null)
      setShortRestInput('')
      prevIdRef.current = selected?.id
    }
  }, [selected?.id])

  const effectiveHp = hpLocal ?? selected?.hp ?? { current: 0, max: 0 }
  const effectiveSlots: Record<string, {max: number; used: number; level?: number}> = (() => {
    if (slotsLocal) return slotsLocal
    const fromSheet = selected?.spellSlots ?? {}
    if (Object.keys(fromSheet).length > 0) return fromSheet
    return computeStandardSlots(selected?.class_name, selected?.level)
  })()
  const effectiveInv: string[] = invLocal ?? (selected?.inventory ?? [])

  // Prepared overrides: local changes layered on top of server-persisted overrides
  const effectivePreparedOverrides: Record<string, boolean> = {
    ...(selected?.preparedOverrides ?? {}),
    ...(preparedOverridesLocal ?? {}),
  }
  const getPrepared = (spellName: string, basePrepared: boolean | null): boolean | null => {
    if (spellName in effectivePreparedOverrides) return effectivePreparedOverrides[spellName]
    return basePrepared
  }
  const togglePrepared = (spellName: string, currentPrepared: boolean | null) => {
    const next = !(currentPrepared === true)
    const newOverrides = { ...effectivePreparedOverrides, [spellName]: next }
    setPreparedOverridesLocal(newOverrides)
    pushSheetPatch({ prepared_spell_overrides: newOverrides })
  }
  const ORD_LEVELS = ['', '1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th', '9th']
  const addSpellToBook = (name?: string, level?: number) => {
    const spellName = (name ?? addSpellName).trim()
    const spellLevel = level ?? addSpellLevel
    if (!spellName || !selected?.id) return
    const currentBook = Array.isArray(selected?.spellbook) ? [...selected.spellbook] : []
    const levelHeader = spellLevel === 0 ? 'Cantrips' : `${ORD_LEVELS[spellLevel] ?? `${spellLevel}th`} Level`
    const newEntry = { name: spellName, header: levelHeader, prepared: null, concentration: false, ritual: false }
    pushSheetPatch({ spellbook: [...currentBook, newEntry] })
    setAddSpellName('')
    setShowAddSpell(false)
  }

  // Session document content for content-aware search
  const [sessionDocContent, setSessionDocContent] = useState('')
  const [docsFetched, setDocsFetched] = useState(false)
  useEffect(() => {
    if (!sessionId || docsFetched) return
    setDocsFetched(true)
    apiFetch(`/documents/${sessionId}`).then(async r => {
      if (!r.ok) return
      const docs = await r.json() as any[]
      const shared = docs.filter(d => d.visibility !== 'hidden').slice(0, 12)
      const texts = await Promise.allSettled(
        shared.map(async (d: any) => {
          const dr = await apiFetch(`/documents/${sessionId}/${d.id}`)
          if (!dr.ok) return ''
          const dd = await dr.json()
          return String(dd.content ?? '')
        })
      )
      setSessionDocContent(
        texts.filter(r => r.status === 'fulfilled').map(r => (r as PromiseFulfilledResult<string>).value).join('\n')
      )
    }).catch(() => {})
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, docsFetched])

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

        {/* Status indicators (exhaustion / concentration / death saves — only when relevant) */}
        {(showDeathSaves || showExhaustion || concentratingOn) ? (
          <div className="cs-status-row">
            {concentratingOn ? (
              <div className="cs-status-badge cs-status-badge--conc">
                <span className="cs-conc-label">Conc:</span> {concentratingOn}
                <button type="button" className="cs-status-clear" onClick={() => setConcentratingOn(null)} title="Drop concentration">✕</button>
              </div>
            ) : null}
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
              // Caster type detection
              const KNOWN_CASTERS = /sorcerer|bard|ranger|warlock|eldritch\s*knight|arcane\s*trickster/i
              const PREPARED_CASTERS = /cleric|druid|paladin|wizard|artificer/i
              const PACT_CASTERS = /warlock/i
              const cn = selected?.class_name ?? ''
              const casterType: 'prepared' | 'known' | 'unknown' =
                PREPARED_CASTERS.test(cn) ? 'prepared' :
                KNOWN_CASTERS.test(cn) ? 'known' : 'unknown'
              const isPactCaster = PACT_CASTERS.test(cn)

              // Build spell entries
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

              type SpellEntry = {
                name: string; level: number; prepared: boolean | null
                concentration: boolean; ritual: boolean
                save_hit?: string; time?: string; range?: string
                components?: string; duration?: string; notes?: string
              }

              let entries: SpellEntry[] = []
              if (book.length > 0) {
                let currentLevel = 1
                for (const e of book) {
                  if (!e) continue
                  if (e.header) currentLevel = parseLevelFromHeader(String(e.header))
                  if (!e.name) continue
                  const p = e.prepared
                  const basePrepared: boolean | null =
                    p === true || p === 'yes' || p === 1 ? true :
                    p === false || p === 'no' || p === 0 ? false : null
                  entries.push({
                    name: String(e.name), level: currentLevel,
                    prepared: getPrepared(String(e.name), basePrepared),
                    concentration: Boolean(e.concentration),
                    ritual: Boolean(e.ritual),
                    save_hit: e.save_hit ? String(e.save_hit) : undefined,
                    time: e.time ? String(e.time) : undefined,
                    range: e.range ? String(e.range) : undefined,
                    components: e.components ? String(e.components) : undefined,
                    duration: e.duration ? String(e.duration) : undefined,
                    notes: e.notes ? String(e.notes) : undefined,
                  })
                }
              } else {
                entries = (selected?.spells ?? []).map((name: string) => ({
                  name, level: 1, prepared: null, concentration: false, ritual: false,
                }))
              }

              if (!entries.length) return <div className="cs-empty">No spells recorded</div>

              const isCastable = (spell: SpellEntry): boolean => {
                if (spell.level === 0) return true
                if (casterType === 'known') return true
                if (casterType === 'prepared') return spell.prepared === true
                return true
              }
              // Group entries by level for the Known section
              const knownByLevel = new Map<number, SpellEntry[]>()
              for (const e of entries) {
                if (!knownByLevel.has(e.level)) knownByLevel.set(e.level, [])
                knownByLevel.get(e.level)!.push(e)
              }
              const knownLevels = Array.from(knownByLevel.keys()).sort((a, b) => a - b)

              const filteredEntries = entries.filter(spell => {
                if (spellFilter === 'ritual') return spell.ritual
                if (spellFilter === 'castable') return isCastable(spell)
                return true
              })

              const grouped = new Map<number, SpellEntry[]>()
              for (const e of filteredEntries) {
                if (!grouped.has(e.level)) grouped.set(e.level, [])
                grouped.get(e.level)!.push(e)
              }
              const levels = Array.from(grouped.keys()).sort((a, b) => a - b)

              const levelLabel = (n: number) => {
                if (n === 0) return 'Cantrips'
                const ord = ['', '1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th', '9th'][n] ?? `${n}th`
                return `${ord} Level`
              }

              // Core cast execution (slot marked + concentration tracked)
              const doCast = (spell: SpellEntry, slotLevel: number | null) => {
                if (slotLevel !== null && slotLevel > 0) {
                  const pactEntry = Object.entries(effectiveSlots).find(([k]) => k === 'pact')
                  const pactLevel = pactEntry ? (pactEntry[1].level ?? 0) : 0
                  const slotKey = isPactCaster && pactLevel === slotLevel ? 'pact' : String(slotLevel)
                  markSlotUsed(slotKey)
                }
                if (spell.concentration) setConcentratingOn(spell.name)
                onQuickAction?.({ type: 'cast', detail: spell.name })
                setExpandedSpell(null)
                setSpellUpcastOptions(null)
                setConcWarning(null)
              }

              // Guard concentration conflict, then execute
              const withConcCheck = (spell: SpellEntry, action: () => void) => {
                if (spell.concentration && concentratingOn && concentratingOn !== spell.name) {
                  setConcWarning({ spell: spell.name, action })
                } else {
                  action()
                }
              }

              const handleCastFromDetail = (spell: SpellEntry, isRitual: boolean = false) => {
                if (isRitual) {
                  withConcCheck(spell, () => {
                    if (spell.concentration) setConcentratingOn(spell.name)
                    onQuickAction?.({ type: 'cast', detail: `${spell.name} (ritual)` })
                    setExpandedSpell(null)
                    setConcWarning(null)
                  })
                  return
                }
                if (spell.level === 0) { withConcCheck(spell, () => doCast(spell, null)); return }
                const available = Object.entries(effectiveSlots)
                  .filter(([lvl, s]) => {
                    const n = lvl === 'pact' ? (s.level ?? 0) : Number(lvl)
                    return n >= spell.level && s.used < s.max
                  })
                  .map(([lvl, s]) => lvl === 'pact' ? (s.level ?? 0) : Number(lvl))
                  .filter(n => n > 0)
                  .sort((a, b) => a - b)
                if (!available.length) { withConcCheck(spell, () => doCast(spell, null)); return }
                if (available.length === 1) { withConcCheck(spell, () => doCast(spell, available[0])); return }
                setSpellUpcastOptions({ spell: spell.name, minLevel: spell.level, options: available })
              }

              const preparedCount = casterType === 'prepared'
                ? entries.filter(e => e.level > 0 && e.prepared === true).length : null

              return (
                <div className="cs-spell-book">
                  {/* Filter bar */}
                  <div className="cs-spell-filter-bar">
                    {(['castable', 'all', 'ritual'] as const).map(f => (
                      <button
                        key={f}
                        type="button"
                        className={`cs-spell-filter-btn ${spellFilter === f ? 'cs-spell-filter-btn--active' : ''}`}
                        onClick={() => { setSpellFilter(f); setExpandedSpell(null); setSpellUpcastOptions(null) }}
                      >
                        {f === 'castable' ? 'Castable' : f === 'all' ? 'All' : 'Rituals'}
                      </button>
                    ))}
                    {preparedCount !== null ? (
                      <span className="cs-spell-prep-count">{preparedCount} prepared</span>
                    ) : null}
                  </div>

                  {/* Concentration conflict warning */}
                  {concWarning ? (
                    <div className="cs-conc-warning">
                      <span>End <em>{concentratingOn}</em> to cast <em>{concWarning.spell}</em>?</span>
                      <div className="cs-conc-warning-btns">
                        <button type="button" className="cs-conc-confirm" onClick={() => {
                          setConcentratingOn(null)
                          concWarning.action()
                        }}>Confirm</button>
                        <button type="button" className="cs-conc-cancel" onClick={() => setConcWarning(null)}>Cancel</button>
                      </div>
                    </div>
                  ) : null}

                  {!filteredEntries.length ? (
                    <div className="cs-empty">No spells match this filter</div>
                  ) : null}

                  {levels.map(lvl => {
                    const spellsAtLevel = grouped.get(lvl)!
                    const pactEntry = Object.entries(effectiveSlots).find(([k]) => k === 'pact')
                    const pactLevel = pactEntry ? (pactEntry[1].level ?? 0) : 0
                    const usePactSlot = isPactCaster && lvl > 0 && pactLevel === lvl
                    const slot = lvl > 0 ? (effectiveSlots[usePactSlot ? 'pact' : String(lvl)] ?? null) : null
                    const slotsAvail = slot ? slot.max - slot.used : null

                    return (
                      <div key={lvl} className="cs-spell-level-group">
                        <div className="cs-spell-level-header">
                          <span className="cs-spell-level-label">{levelLabel(lvl)}</span>
                          {slot && slot.max > 0 ? (
                            <div className={`cs-spell-slot-pips-row ${usePactSlot ? 'cs-spell-slot-pips-row--pact' : ''}`}>
                              {usePactSlot ? <span className="cs-spell-slot-label-sm">Pact</span> : null}
                              {Array.from({length: slot.max}).map((_, i) => {
                                const isUsed = i < slot.used
                                const slotK = usePactSlot ? 'pact' : String(lvl)
                                return (
                                  <button
                                    key={i}
                                    type="button"
                                    className={`cs-spell-slot-pip ${isUsed ? 'cs-spell-slot-pip--used' : ''}`}
                                    title={isUsed ? 'Restore slot' : 'Use slot'}
                                    onClick={e => {
                                      e.stopPropagation()
                                      const newUsed = isUsed ? i : i + 1
                                      applySlots({...effectiveSlots, [slotK]: {...slot, used: newUsed}})
                                    }}
                                  />
                                )
                              })}
                              <span className="cs-spell-slot-count">{slotsAvail}/{slot.max}</span>
                            </div>
                          ) : null}
                        </div>
                        {spellsAtLevel.map(spell => {
                          const isExpanded = expandedSpell === spell.name
                          const isUpcastTarget = spellUpcastOptions?.spell === spell.name
                          const castable = isCastable(spell)
                          return (
                            <div key={spell.name} className={`cs-spell-item ${isExpanded ? 'cs-spell-item--open' : ''} ${!castable ? 'cs-spell-item--dim' : ''}`}>
                              <button
                                type="button"
                                className="cs-spell-name-btn"
                                onClick={() => {
                                  setExpandedSpell(prev => prev === spell.name ? null : spell.name)
                                  setSpellUpcastOptions(null)
                                  setConcWarning(null)
                                }}
                              >
                                <span className="cs-spell-name">{spell.name}</span>
                                <span className="cs-spell-badges">
                                  {spell.prepared === true ? <span className="cs-spell-badge cs-spell-badge--prep" title="Prepared">◆</span> : null}
                                  {spell.prepared === false && spellFilter === 'all' ? <span className="cs-spell-badge cs-spell-badge--unprep" title="Not prepared">◇</span> : null}
                                  {spell.concentration ? <span className="cs-spell-badge cs-spell-badge--conc" title="Concentration">C</span> : null}
                                  {spell.ritual ? <span className="cs-spell-badge cs-spell-badge--ritual" title="Ritual">R</span> : null}
                                </span>
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
                                  {!castable && casterType === 'prepared' ? (
                                    <div className="cs-spell-not-prepared">Not prepared — cannot cast this rest</div>
                                  ) : isUpcastTarget ? (
                                    <div className="cs-spell-upcast">
                                      <div className="cs-spell-upcast-label">Cast at level:</div>
                                      <div className="cs-spell-upcast-options">
                                        {spellUpcastOptions!.options.map(lvlOpt => (
                                          <button
                                            key={lvlOpt}
                                            type="button"
                                            className="cs-spell-upcast-btn"
                                            onClick={() => withConcCheck(spell, () => doCast(spell, lvlOpt))}
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
                                    <div className="cs-spell-actions">
                                      <button
                                        type="button"
                                        className="cs-spell-cast-btn"
                                        onClick={() => handleCastFromDetail(spell)}
                                      >
                                        {spell.level === 0 ? '✦ Cast Cantrip' : slotsAvail === 0 ? '✦ Cast (no slots)' : '✦ Cast'}
                                      </button>
                                      {spell.ritual ? (
                                        <button
                                          type="button"
                                          className="cs-spell-cast-btn cs-spell-cast-btn--ritual"
                                          onClick={() => handleCastFromDetail(spell, true)}
                                          title="No slot required — takes 10 extra minutes"
                                        >
                                          Ritual
                                        </button>
                                      ) : null}
                                    </div>
                                  )}
                                </div>
                              ) : null}
                            </div>
                          )
                        })}
                      </div>
                    )
                  })}

                  {/* All Known Spells — collapsible management section */}
                  {spellFilter !== 'ritual' ? (
                    <div className="cs-known-section">
                      <button
                        type="button"
                        className="cs-known-toggle"
                        onClick={() => setShowAllKnown(v => !v)}
                      >
                        <span>All Known Spells ({entries.length})</span>
                        <span className="cs-known-chevron">{showAllKnown ? '▲' : '▼'}</span>
                      </button>
                      {showAllKnown ? (
                        <div className="cs-known-list">
                          {knownLevels.map(lvl => (
                            <div key={lvl} className="cs-known-level-group">
                              <div className="cs-known-level-label">{levelLabel(lvl)}</div>
                              {knownByLevel.get(lvl)!.map(spell => (
                                <div key={spell.name} className="cs-known-row">
                                  <span className="cs-known-name">{spell.name}</span>
                                  {spell.concentration ? <span className="cs-spell-badge cs-spell-badge--conc" title="Concentration">C</span> : null}
                                  {spell.ritual ? <span className="cs-spell-badge cs-spell-badge--ritual" title="Ritual">R</span> : null}
                                  {lvl > 0 && casterType === 'prepared' ? (
                                    <button
                                      type="button"
                                      className={`cs-prep-toggle ${spell.prepared === true ? 'cs-prep-toggle--prepared' : ''}`}
                                      onClick={() => togglePrepared(spell.name, spell.prepared)}
                                      title={spell.prepared === true ? 'Click to unprepare' : 'Click to prepare'}
                                    >
                                      {spell.prepared === true ? '◆ Prepared' : '◇ Prepare'}
                                    </button>
                                  ) : null}
                                </div>
                              ))}
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ) : null}

                  {/* Add spell — content browser */}
                  <div className="cs-add-spell-section">
                    {showAddSpell ? (() => {
                      const q = addSpellName.toLowerCase()
                      const existingNames = new Set(entries.map(e => e.name.toLowerCase()))
                      // Spells from character's PDF (may not be in active list)
                      const allBookEntries: SpellEntry[] = (() => {
                        const book = Array.isArray(selected?.spellbook) ? selected!.spellbook : []
                        const seen = new Set<string>()
                        const out: SpellEntry[] = []
                        let lvl = 1
                        for (const e of book) {
                          if (!e) continue
                          if (e.header) lvl = parseLevelFromHeader(String(e.header))
                          if (!e.name) continue
                          const nm = String(e.name)
                          if (!seen.has(nm)) {
                            seen.add(nm)
                            out.push({ name: nm, level: lvl, prepared: null, concentration: false, ritual: false })
                          }
                        }
                        return out
                      })()
                      const sheetMatches = q
                        ? allBookEntries.filter(e => e.name.toLowerCase().includes(q)).slice(0, 8)
                        : []
                      // Spells from session documents (text search for lines matching query)
                      const docMatches: string[] = q && sessionDocContent
                        ? Array.from(new Set(
                            sessionDocContent.split('\n')
                              .map(l => l.trim())
                              .filter(l => l.length > 2 && l.length < 70 && l.toLowerCase().includes(q) && !existingNames.has(l.toLowerCase()))
                          )).slice(0, 6)
                        : []
                      return (
                        <div className="cs-content-browser">
                          <div className="cs-content-browser-header">
                            <input
                              autoFocus
                              className="cs-content-search"
                              type="text"
                              placeholder="Search your sheet & session docs…"
                              value={addSpellName}
                              onChange={e => setAddSpellName(e.target.value)}
                            />
                            <button type="button" className="cs-content-browser-close" onClick={() => { setShowAddSpell(false); setAddSpellName('') }}>✕</button>
                          </div>
                          {sheetMatches.length > 0 ? (
                            <div className="cs-content-section">
                              <div className="cs-content-section-label">From your character sheet</div>
                              {sheetMatches.map(spell => (
                                <button
                                  key={spell.name}
                                  type="button"
                                  className="cs-content-result"
                                  onClick={() => addSpellToBook(spell.name, spell.level)}
                                >
                                  <span className="cs-content-result-name">{spell.name}</span>
                                  <span className="cs-content-result-meta">{levelLabel(spell.level)}</span>
                                </button>
                              ))}
                            </div>
                          ) : null}
                          {docMatches.length > 0 ? (
                            <div className="cs-content-section">
                              <div className="cs-content-section-label">From session documents</div>
                              {docMatches.map(name => (
                                <button
                                  key={name}
                                  type="button"
                                  className="cs-content-result"
                                  onClick={() => addSpellToBook(name, addSpellLevel)}
                                >
                                  <span className="cs-content-result-name">{name}</span>
                                  <span className="cs-content-result-meta cs-content-result-meta--doc">doc</span>
                                </button>
                              ))}
                            </div>
                          ) : null}
                          {/* Manual add at bottom */}
                          <div className="cs-content-manual">
                            <select
                              className="cs-add-spell-level"
                              value={addSpellLevel}
                              onChange={e => setAddSpellLevel(Number(e.target.value))}
                            >
                              <option value={0}>Cantrip</option>
                              {[1,2,3,4,5,6,7,8,9].map(l => <option key={l} value={l}>Level {l}</option>)}
                            </select>
                            <button
                              type="button"
                              className="cs-add-spell-btn"
                              disabled={!addSpellName.trim()}
                              onClick={() => addSpellToBook()}
                            >
                              + Add {addSpellName.trim() ? `"${addSpellName.trim()}"` : 'spell'}
                            </button>
                          </div>
                        </div>
                      )
                    })() : (
                      <button
                        type="button"
                        className="cs-add-spell-trigger"
                        onClick={() => setShowAddSpell(true)}
                      >+ Add Spell</button>
                    )}
                  </div>
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
                  <div className="cs-inv-add-row">
                    <input
                      className="cs-inv-add-input"
                      type="text"
                      placeholder="Add item from sheet or session…"
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
                  {/* Content suggestions from session documents */}
                  {addItemInput.trim().length >= 2 && sessionDocContent ? (() => {
                    const q = addItemInput.trim().toLowerCase()
                    const currentSet = new Set(effectiveInv.map(i => i.toLowerCase()))
                    const suggestions = Array.from(new Set(
                      sessionDocContent.split('\n')
                        .map(l => l.trim())
                        .filter(l => l.length > 2 && l.length < 60 && l.toLowerCase().includes(q) && !currentSet.has(l.toLowerCase()))
                    )).slice(0, 6)
                    if (!suggestions.length) return null
                    return (
                      <div className="cs-content-section cs-inv-suggestions">
                        <div className="cs-content-section-label">From session documents</div>
                        {suggestions.map(item => (
                          <button
                            key={item}
                            type="button"
                            className="cs-content-result"
                            onClick={() => {
                              const next = [...effectiveInv, item]
                              setInvLocal(next)
                              pushSheetPatch({ inventory: next })
                              setAddItemInput('')
                            }}
                          >
                            <span className="cs-content-result-name">{item}</span>
                            <span className="cs-content-result-meta cs-content-result-meta--doc">doc</span>
                          </button>
                        ))}
                      </div>
                    )
                  })() : null}
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
