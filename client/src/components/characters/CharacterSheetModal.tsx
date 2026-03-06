import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import Modal from '../ui/Modal'
import { apiFetch, API_BASE } from '../../api'

import './CharacterSheetModal.css'

// Matches section-header names like "Artificer Features", "Core Paladin Traits",
// "Species Abilities", etc.  These should not appear as individual feature items.
const FEATURE_CATEGORY_PATTERN = /\b(features?|traits?|abilities|proficiencies|class\s+features?|racial\s+traits?|species\s+traits?|subclass\s+features?)\s*$/i
const FEATURE_SKIP_NAMES = new Set(['proficiencies', 'features', 'traits', 'abilities', 'other proficiencies & languages', 'other proficiencies and languages', 'class features', 'racial traits', 'species traits'])

function isFeatureCategoryHeader(name: string): boolean {
  const lower = name.toLowerCase().trim()
  if (FEATURE_SKIP_NAMES.has(lower)) return true
  // Heuristic: names ending in "Features", "Traits", etc. are section headers, not features.
  // The colon exclusion preserves items like "Infuse Item: Bag of Holding" which are real
  // feature names that happen to describe a specific invocation or application.
  if (FEATURE_CATEGORY_PATTERN.test(name) && !name.includes(':')) return true
  return false
}

/** Extract a display name string from a feature value that may be a string or an object. */
function featureItemName(v: any): string {
  if (typeof v === 'string') return v.trim()
  if (v && typeof v === 'object') return asString((v as any).name).trim()
  return ''
}

type Character = {
  id: number
  name: string
  level: number
  class_name?: string | null
  sheet?: any
}

type Props = {
  open: boolean
  character: Character | null
  loading?: boolean
  onClose: () => void
  onSaved?: () => void | Promise<void>
  embedded?: boolean
}

function asString(v: any): string {
  return typeof v === 'string' ? v : v == null ? '' : String(v)
}

function asNumber(v: any, fallback: number): number {
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : fallback
}

function joinList(value: any): string[] {
  if (!Array.isArray(value)) return []
  return value.map((v) => asString(v)).map((s) => s.trim()).filter(Boolean)
}

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value))
}

function uniqNonEmpty(values: string[]): string[] {
  const out: string[] = []
  const seen = new Set<string>()
  for (const v of values) {
    const s = asString(v).trim()
    if (!s) continue
    if (seen.has(s)) continue
    seen.add(s)
    out.push(s)
  }
  return out
}

function pick(obj: any, path: Array<string | number>): any {
  let cur = obj
  for (const key of path) {
    if (!cur || typeof cur !== 'object') return undefined
    cur = (cur as any)[key as any]
  }
  return cur
}

function toStringListLoose(value: any): string[] {
  if (!value) return []
  if (Array.isArray(value)) {
    const items = value
      .map((v) => {
        if (typeof v === 'string' || typeof v === 'number') return String(v)
        if (v && typeof v === 'object') {
          return (
            asString((v as any).name) ||
            asString(pick(v, ['definition', 'name'])) ||
            asString(pick(v, ['spell', 'name'])) ||
            asString(pick(v, ['item', 'name'])) ||
            ''
          )
        }
        return ''
      })
      .map((s) => s.trim())
      .filter(Boolean)
    return uniqNonEmpty(items)
  }
  if (typeof value === 'string') return value.trim() ? [value.trim()] : []
  return []
}

type InventoryItem = {
  name: string
  quantity?: number | null
  type?: string | null
  weight?: number | null
  cost?: string | null
  notes?: string | null
}

type SpellSlot = {
  level: number
  used?: number | null
  max?: number | null
}

function inferMovementFromRaw(raw: any): Record<string, number | null> {
  if (!raw || typeof raw !== 'object') return { walk: null, fly: null, swim: null, climb: null, burrow: null }
  const speedObj = pick(raw, ['speed']) ?? pick(raw, ['movement']) ?? pick(raw, ['speeds'])
  if (speedObj && typeof speedObj === 'object') {
    const walk = asNumber((speedObj as any).walk ?? (speedObj as any).walking ?? (speedObj as any).base, NaN)
    const fly = asNumber((speedObj as any).fly ?? (speedObj as any).flying, NaN)
    const swim = asNumber((speedObj as any).swim ?? (speedObj as any).swimming, NaN)
    const climb = asNumber((speedObj as any).climb ?? (speedObj as any).climbing, NaN)
    const burrow = asNumber((speedObj as any).burrow ?? (speedObj as any).burrowing, NaN)
    return {
      walk: Number.isFinite(walk) ? walk : null,
      fly: Number.isFinite(fly) ? fly : null,
      swim: Number.isFinite(swim) ? swim : null,
      climb: Number.isFinite(climb) ? climb : null,
      burrow: Number.isFinite(burrow) ? burrow : null,
    }
  }
  const walk = asNumber(pick(raw, ['speed']), NaN)
  return { walk: Number.isFinite(walk) ? walk : null, fly: null, swim: null, climb: null, burrow: null }
}

function inferDeathSavesFromRaw(raw: any): { successes: number | null; failures: number | null } {
  if (!raw || typeof raw !== 'object') return { successes: null, failures: null }
  const ds = pick(raw, ['deathSaves']) ?? pick(raw, ['death_saves']) ?? pick(raw, ['deathsave'])
  if (ds && typeof ds === 'object') {
    const successes = asNumber((ds as any).successes ?? (ds as any).success ?? (ds as any).successCount, NaN)
    const failures = asNumber((ds as any).failures ?? (ds as any).failure ?? (ds as any).failureCount, NaN)
    return {
      successes: Number.isFinite(successes) ? successes : null,
      failures: Number.isFinite(failures) ? failures : null,
    }
  }
  return { successes: null, failures: null }
}

function inferRestStateFromRaw(raw: any): { hitDiceUsed: number | null; hitDiceTotal: number | null; inspiration: boolean | null; exhaustion: number | null } {
  if (!raw || typeof raw !== 'object') return { hitDiceUsed: null, hitDiceTotal: null, inspiration: null, exhaustion: null }
  const hitDiceUsed = asNumber(pick(raw, ['hitDiceUsed']) ?? pick(raw, ['hit_dice_used']) ?? pick(raw, ['hitDice', 'used']), NaN)
  const hitDiceTotal = asNumber(
    pick(raw, ['hitDiceTotal']) ?? pick(raw, ['hit_dice_total']) ?? pick(raw, ['hitDice', 'total']) ?? pick(raw, ['hitDice', 'max']),
    NaN
  )
  const inspirationRaw = pick(raw, ['inspiration']) ?? pick(raw, ['hasInspiration']) ?? pick(raw, ['inspired'])
  const exhaustion = asNumber(pick(raw, ['exhaustion']) ?? pick(raw, ['exhaustionLevel']), NaN)
  return {
    hitDiceUsed: Number.isFinite(hitDiceUsed) ? hitDiceUsed : null,
    hitDiceTotal: Number.isFinite(hitDiceTotal) ? hitDiceTotal : null,
    inspiration: typeof inspirationRaw === 'boolean' ? inspirationRaw : null,
    exhaustion: Number.isFinite(exhaustion) ? exhaustion : null,
  }
}

function inferSpellSlotsFromRaw(raw: any): SpellSlot[] {
  if (!raw || typeof raw !== 'object') return []
  const candidates = [
    pick(raw, ['spellSlots']),
    pick(raw, ['spell_slots']),
    pick(raw, ['spellSlotsByLevel']),
    pick(raw, ['spellslots']),
  ].filter(Boolean)

  const slots: SpellSlot[] = []

  for (const c of candidates) {
    if (Array.isArray(c)) {
      for (const entry of c) {
        if (!entry || typeof entry !== 'object') continue
        const level = asNumber((entry as any).level ?? (entry as any).spellLevel ?? (entry as any).lvl, NaN)
        if (!Number.isFinite(level) || level < 1 || level > 9) continue
        const max = asNumber((entry as any).max ?? (entry as any).total ?? (entry as any).available, NaN)
        const used = asNumber((entry as any).used ?? (entry as any).spent, NaN)
        slots.push({ level, max: Number.isFinite(max) ? max : null, used: Number.isFinite(used) ? used : null })
      }
    } else if (c && typeof c === 'object') {
      for (const [key, value] of Object.entries(c as any)) {
        const level = asNumber(key, NaN)
        if (!Number.isFinite(level) || level < 1 || level > 9) continue
        if (value && typeof value === 'object') {
          const max = asNumber((value as any).max ?? (value as any).total ?? (value as any).available, NaN)
          const used = asNumber((value as any).used ?? (value as any).spent, NaN)
          slots.push({ level, max: Number.isFinite(max) ? max : null, used: Number.isFinite(used) ? used : null })
        } else {
          const max = asNumber(value as any, NaN)
          slots.push({ level, max: Number.isFinite(max) ? max : null, used: null })
        }
      }
    }
  }

  const merged = new Map<number, SpellSlot>()
  for (const slot of slots) {
    const existing = merged.get(slot.level)
    merged.set(slot.level, {
      level: slot.level,
      max: existing?.max ?? slot.max ?? null,
      used: existing?.used ?? slot.used ?? null,
    })
  }
  return Array.from(merged.values()).sort((a, b) => a.level - b.level)
}

function inferFeaturesFromRaw(raw: any): { classFeatures: string[]; racialFeatures: string[]; otherFeatures: string[] } {
  if (!raw || typeof raw !== 'object') return { classFeatures: [], racialFeatures: [], otherFeatures: [] }

  const classFeatures = uniqNonEmpty([
    ...toStringListLoose(pick(raw, ['classFeatures'])),
    ...toStringListLoose(pick(raw, ['class', 'features'])),
    ...toStringListLoose(pick(raw, ['classes', 'features'])),
  ])

  const racialFeatures = uniqNonEmpty([
    ...toStringListLoose(pick(raw, ['race', 'racialTraits'])),
    ...toStringListLoose(pick(raw, ['race', 'traits'])),
    ...toStringListLoose(pick(raw, ['racialTraits'])),
    ...toStringListLoose(pick(raw, ['raceFeatures'])),
  ])

  const otherFeatures = uniqNonEmpty([
    ...toStringListLoose(pick(raw, ['features'])),
    ...toStringListLoose(pick(raw, ['feats'])),
    ...toStringListLoose(pick(raw, ['traits'])),
  ])

  return { classFeatures, racialFeatures, otherFeatures }
}

function inferInventoryFromRaw(raw: any): InventoryItem[] {
  if (!raw || typeof raw !== 'object') return []
  const candidates = [
    pick(raw, ['inventory']),
    pick(raw, ['items']),
    pick(raw, ['equipment']),
    pick(raw, ['inventory', 'items']),
  ].filter(Boolean)

  const items: InventoryItem[] = []
  for (const c of candidates) {
    if (!Array.isArray(c)) continue
    for (const entry of c) {
      if (!entry) continue
      if (typeof entry === 'string' || typeof entry === 'number') {
        items.push({ name: String(entry) })
        continue
      }
      if (typeof entry === 'object') {
        const def = (entry as any).definition || (entry as any).item || {}
        const name = asString((entry as any).name) || asString(def?.name)
        if (!name) continue
        const quantity = asNumber((entry as any).quantity ?? (entry as any).qty, NaN)
        const weight = asNumber((entry as any).weight ?? def?.weight, NaN)
        const type = asString(def?.type ?? def?.itemType ?? (entry as any).type)
        const costValue = def?.cost?.quantity ?? def?.cost
        const costUnit = def?.cost?.unit ?? ''
        const cost = costValue ? `${costValue}${costUnit ? ` ${costUnit}` : ''}` : ''
        const notes = asString((entry as any).notes ?? def?.description)
        items.push({
          name,
          quantity: Number.isFinite(quantity) ? quantity : null,
          type: type || null,
          weight: Number.isFinite(weight) ? weight : null,
          cost: cost || null,
          notes: notes || null,
        })
      }
    }
  }

  const deduped: InventoryItem[] = []
  const seen = new Set<string>()
  for (const item of items) {
    const key = `${item.name}|${item.type || ''}|${item.cost || ''}|${item.weight || ''}`
    if (seen.has(key)) continue
    seen.add(key)
    deduped.push(item)
  }
  return deduped
}

function ddbStatsArrayToAbilities(raw: any): { str: number | null; dex: number | null; con: number | null; int: number | null; wis: number | null; cha: number | null } {
  const empty = { str: null, dex: null, con: null, int: null, wis: null, cha: null }
  const stats = pick(raw, ['stats'])
  if (!Array.isArray(stats)) return empty
  const bonusStats = Array.isArray(pick(raw, ['bonusStats'])) ? pick(raw, ['bonusStats']) : []
  const overrideStats = Array.isArray(pick(raw, ['overrideStats'])) ? pick(raw, ['overrideStats']) : []

  const getById = (arr: any[], id: number): any | null => arr.find((s) => Number((s as any)?.id) === id) ?? null
  const scoreForId = (id: number): number | null => {
    const base = getById(stats, id)
    const override = getById(overrideStats, id)
    const bonus = getById(bonusStats, id)
    const baseVal = base ? asNumber((base as any).value, NaN) : NaN
    const overrideVal = override ? asNumber((override as any).value, NaN) : NaN
    const bonusVal = bonus ? asNumber((bonus as any).value, 0) : 0
    if (Number.isFinite(overrideVal)) return overrideVal
    if (Number.isFinite(baseVal)) return baseVal + (Number.isFinite(bonusVal) ? bonusVal : 0)
    return null
  }

  return {
    str: scoreForId(1),
    dex: scoreForId(2),
    con: scoreForId(3),
    int: scoreForId(4),
    wis: scoreForId(5),
    cha: scoreForId(6),
  }
}

function inferAbilitiesFromRaw(raw: any): { str: number | null; dex: number | null; con: number | null; int: number | null; wis: number | null; cha: number | null } {
  const empty = { str: null, dex: null, con: null, int: null, wis: null, cha: null }
  if (!raw || typeof raw !== 'object') return empty

  // DDB export shape: raw.stats is an array with ids.
  const ddb = ddbStatsArrayToAbilities(raw)
  if (Object.values(ddb).some((v) => typeof v === 'number' && Number.isFinite(v))) return ddb

  // Common generic shapes.
  const statsObj = pick(raw, ['stats'])
  if (statsObj && typeof statsObj === 'object' && !Array.isArray(statsObj)) {
    const str = asNumber((statsObj as any).str ?? (statsObj as any).strength, NaN)
    const dex = asNumber((statsObj as any).dex ?? (statsObj as any).dexterity, NaN)
    const con = asNumber((statsObj as any).con ?? (statsObj as any).constitution, NaN)
    const int = asNumber((statsObj as any).int ?? (statsObj as any).intelligence, NaN)
    const wis = asNumber((statsObj as any).wis ?? (statsObj as any).wisdom, NaN)
    const cha = asNumber((statsObj as any).cha ?? (statsObj as any).charisma, NaN)
    return {
      str: Number.isFinite(str) ? str : null,
      dex: Number.isFinite(dex) ? dex : null,
      con: Number.isFinite(con) ? con : null,
      int: Number.isFinite(int) ? int : null,
      wis: Number.isFinite(wis) ? wis : null,
      cha: Number.isFinite(cha) ? cha : null,
    }
  }

  const abilitiesObj = pick(raw, ['abilities'])
  if (abilitiesObj && typeof abilitiesObj === 'object' && !Array.isArray(abilitiesObj)) {
    const str = asNumber((abilitiesObj as any).str ?? (abilitiesObj as any).strength, NaN)
    const dex = asNumber((abilitiesObj as any).dex ?? (abilitiesObj as any).dexterity, NaN)
    const con = asNumber((abilitiesObj as any).con ?? (abilitiesObj as any).constitution, NaN)
    const int = asNumber((abilitiesObj as any).int ?? (abilitiesObj as any).intelligence, NaN)
    const wis = asNumber((abilitiesObj as any).wis ?? (abilitiesObj as any).wisdom, NaN)
    const cha = asNumber((abilitiesObj as any).cha ?? (abilitiesObj as any).charisma, NaN)
    return {
      str: Number.isFinite(str) ? str : null,
      dex: Number.isFinite(dex) ? dex : null,
      con: Number.isFinite(con) ? con : null,
      int: Number.isFinite(int) ? int : null,
      wis: Number.isFinite(wis) ? wis : null,
      cha: Number.isFinite(cha) ? cha : null,
    }
  }

  return empty
}

function inferHpFromRaw(raw: any): { hpCurrent: number | null; hpMax: number | null } {
  if (!raw || typeof raw !== 'object') return { hpCurrent: null, hpMax: null }
  const currentCandidates = [
    pick(raw, ['hp', 'current']),
    pick(raw, ['hitPoints', 'current']),
    pick(raw, ['currentHitPoints']),
    pick(raw, ['currentHp']),
  ]
  const maxCandidates = [
    pick(raw, ['hp', 'max']),
    pick(raw, ['hitPoints', 'max']),
    pick(raw, ['maxHitPoints']),
    pick(raw, ['maxHp']),
  ]

  const hpCurrentCandidate = currentCandidates
    .map((v) => asNumber(v, NaN))
    .find((n) => Number.isFinite(n) && n >= 0)
  const hpMaxDirectCandidate = maxCandidates
    .map((v) => asNumber(v, NaN))
    .find((n) => Number.isFinite(n) && n > 0)

  // DDB-ish: baseHitPoints + bonusHitPoints (ignores many edge cases, but better than blank)
  const baseHp = asNumber(pick(raw, ['baseHitPoints']), NaN)
  const bonusHp = asNumber(pick(raw, ['bonusHitPoints']), 0)
  const overrideHp = asNumber(pick(raw, ['overrideHitPoints']), NaN)
  const hpMaxFromParts = Number.isFinite(overrideHp)
    ? overrideHp
    : Number.isFinite(baseHp)
      ? baseHp + (Number.isFinite(bonusHp) ? bonusHp : 0)
      : NaN

  const hpMax = (typeof hpMaxDirectCandidate === 'number' && Number.isFinite(hpMaxDirectCandidate))
    ? hpMaxDirectCandidate
    : Number.isFinite(hpMaxFromParts) && hpMaxFromParts > 0
      ? hpMaxFromParts
      : null

  return {
    hpCurrent: (typeof hpCurrentCandidate === 'number' && Number.isFinite(hpCurrentCandidate)) ? hpCurrentCandidate : null,
    hpMax,
  }
}

function inferAcFromRaw(raw: any): number | null {
  if (!raw || typeof raw !== 'object') return null
  const direct = asNumber(pick(raw, ['ac']) ?? pick(raw, ['armorClass']), NaN)
  if (Number.isFinite(direct) && direct > 0) return direct
  const nested = asNumber(pick(raw, ['armorClass', 'value']), NaN)
  if (Number.isFinite(nested) && nested > 0) return nested
  return null
}

function inferListsFromRaw(raw: any): { inventory: string[]; spells: string[]; features: string[] } {
  if (!raw || typeof raw !== 'object') return { inventory: [], spells: [], features: [] }

  // Inventory-ish
  const inventory = uniqNonEmpty([
    ...toStringListLoose(pick(raw, ['inventory'])),
    ...toStringListLoose(pick(raw, ['inventory', 'items'])),
    ...toStringListLoose(pick(raw, ['items'])),
    ...toStringListLoose(pick(raw, ['equipment'])),
  ])

  // Spells: accept common flattened arrays, or nested lists under spellbook/spells
  const spellsRaw = pick(raw, ['spells']) ?? pick(raw, ['spellbook'])
  const spells = (() => {
    if (Array.isArray(spellsRaw) || typeof spellsRaw === 'string') return toStringListLoose(spellsRaw)
    if (spellsRaw && typeof spellsRaw === 'object') {
      const out: string[] = []
      for (const v of Object.values(spellsRaw as any)) {
        out.push(...toStringListLoose(v))
        if (v && typeof v === 'object') out.push(...toStringListLoose(pick(v, ['spells'])))
      }
      return uniqNonEmpty(out)
    }
    return []
  })()

  // Features / feats / traits
  const features = uniqNonEmpty([
    ...toStringListLoose(pick(raw, ['features'])),
    ...toStringListLoose(pick(raw, ['feats'])),
    ...toStringListLoose(pick(raw, ['traits'])),
    ...toStringListLoose(pick(raw, ['classFeatures'])),
  ])

  return { inventory, spells, features }
}

function ListPreview({ title, items, onItemClick }: { title: string; items: string[]; onItemClick?: (item: string) => void }) {
  const limit = 14
  const [expanded, setExpanded] = useState(false)
  const shown = expanded ? items : items.slice(0, limit)
  const remaining = items.length - limit
  return (
    <div className="card tt-sheet-card">
      <div className="muted" style={{ marginBottom: 6 }}>{title}</div>
      <ul style={{ margin: 0, paddingLeft: 18 }}>
        {shown.map((item) => (
          <li key={item}>
            {onItemClick ? (
              <button className="btn btn-ghost" style={{ padding: 0, textAlign: 'left' }} onClick={() => onItemClick(item)}>{item}</button>
            ) : (
              item
            )}
          </li>
        ))}
      </ul>
      {remaining > 0 ? (
        <button
          className="btn btn-quiet"
          style={{ marginTop: 8, fontSize: 12, padding: '2px 4px', color: 'var(--tt-accent, #c084fc)' }}
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? '▲ Show less' : `+ ${remaining} more — Show all`}
        </button>
      ) : null}
    </div>
  )
}

function stripHtml(html: string): string {
  return html
    .replace(/<[^>]*>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, '&')
    .replace(/\s{2,}/g, ' ')
    .trim()
}

function InventoryList({ items }: { items: InventoryItem[] }) {
  if (!items.length) return null
  return (
    <div className="card tt-sheet-card">
      <div className="muted" style={{ marginBottom: 6 }}>Inventory</div>
      <ul style={{ margin: 0, paddingLeft: 18 }}>
        {items.map((item) => (
          <li key={`${item.name}-${item.type || ''}-${item.cost || ''}`}>
            <button className="btn btn-ghost" style={{ padding: 0, textAlign: 'left' }} onClick={() => {
              const rawNotes = item.notes || ''
              const notes = stripHtml(rawNotes) || `${item.name}${item.quantity ? ` x${item.quantity}` : ''}${item.type ? ` • ${item.type}` : ''}${item.weight ? ` • ${item.weight} lb` : ''}${item.cost ? ` • ${item.cost}` : ''}`
              ;(window as any).tt_setDetail && (window as any).tt_setDetail(item.name, notes)
            }}>{item.name}</button>
            {item.quantity ? ` x${item.quantity}` : ''}
            {item.type ? <span className="muted"> • {item.type}</span> : null}
            {item.weight ? <span className="muted"> • {item.weight} lb</span> : null}
            {item.cost ? <span className="muted"> • {item.cost}</span> : null}
            {item.notes ? <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>{stripHtml(item.notes)}</div> : null}
          </li>
        ))}
      </ul>
    </div>
  )
}

type SheetTab = 'overview' | 'bio' | 'spells' | 'features'

export default function CharacterSheetModal({ open, character, loading = false, onClose, onSaved, embedded = false }: Props) {
  const [showRaw, setShowRaw] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editSheet, setEditSheet] = useState<any>(null)
  const [editName, setEditName] = useState('')
  const [editLevel, setEditLevel] = useState('')
  const [editClassName, setEditClassName] = useState('')
  const [saveBusy, setSaveBusy] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailTitle, setDetailTitle] = useState<string | null>(null)
  const [detailText, setDetailText] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<SheetTab>('overview')
  const [localSpellSlots, setLocalSpellSlots] = useState<SpellSlot[]>([])
  const [preparedSpells, setPreparedSpells] = useState<Set<string>>(new Set())
  const [dragSpell, setDragSpell] = useState<string | null>(null)
  const slotSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!open) return
    // Default to the organized view every time you open a sheet.
    setShowRaw(false)
    setActiveTab('overview')
  }, [open, character?.id])

  const sheet = useMemo(() => {
    const candidate = character?.sheet
    return (candidate && typeof candidate === 'object') ? candidate : {}
  }, [character?.sheet])

  const importMeta = useMemo(() => {
    const candidate = (sheet as any)?.import
    return (candidate && typeof candidate === 'object') ? candidate : {}
  }, [sheet])

  const ddbUrl = asString(importMeta?.ddb_url)
  const source = asString(importMeta?.source)

  const pdfMeta = useMemo(() => {
    if (source !== 'pdf') return null
    const widgets = (importMeta?.pdf_widgets && typeof importMeta.pdf_widgets === 'object') ? importMeta.pdf_widgets : {}
    const widgetCount = asNumber((widgets as any)?.count, 0) || null
    const rawTextLen = asNumber(importMeta?.raw_text_len ?? (typeof sheet?.raw_text === 'string' ? sheet.raw_text.length : null), 0) || null
    const extracted = (importMeta?.extracted && typeof importMeta.extracted === 'object') ? importMeta.extracted : {}
    const overrides = (importMeta?.overrides && typeof importMeta.overrides === 'object') ? importMeta.overrides : {}
    return { widgetCount, rawTextLen, extracted, overrides }
  }, [importMeta, sheet, source])

  const derived = useMemo(() => {
    const rawFromSheet = (sheet?.raw && typeof sheet.raw === 'object') ? sheet.raw : {}
    const stats = (sheet?.stats && typeof sheet.stats === 'object') ? sheet.stats : {}
    const importPdfValues = (importMeta?.pdf_widgets && typeof importMeta.pdf_widgets === 'object' && importMeta.pdf_widgets.values && typeof importMeta.pdf_widgets.values === 'object') ? importMeta.pdf_widgets.values : {}

    // Merge sources so inference helpers find values regardless of where importer placed them.
    const mergedRaw: any = { ...rawFromSheet, ...importPdfValues }

    // Ensure canonical stats/HP/AC are present under common keys the inference expects.
    if (sheet?.stats && typeof sheet.stats === 'object') mergedRaw.stats = { ...(mergedRaw.stats || {}), ...sheet.stats }
    if (typeof sheet?.ac !== 'undefined' && (mergedRaw.ac === undefined || mergedRaw.ac === null)) mergedRaw.ac = sheet.ac
    if (sheet?.hp && typeof sheet.hp === 'object') {
      mergedRaw.hp = { ...(mergedRaw.hp || {}), ...(sheet.hp || {}) }
      // legacy keys
      mergedRaw.hitPoints = mergedRaw.hitPoints || {}
      mergedRaw.hitPoints.current = mergedRaw.hitPoints.current ?? mergedRaw.hp.current ?? sheet.hp.current ?? sheet.hp_current
      mergedRaw.hitPoints.max = mergedRaw.hitPoints.max ?? mergedRaw.hp.max ?? sheet.hp.max ?? sheet.hp_max
      mergedRaw.currentHitPoints = mergedRaw.currentHitPoints ?? mergedRaw.hitPoints.current
      mergedRaw.maxHitPoints = mergedRaw.maxHitPoints ?? mergedRaw.hitPoints.max
      mergedRaw.currentHp = mergedRaw.currentHp ?? mergedRaw.currentHitPoints
      mergedRaw.maxHp = mergedRaw.maxHp ?? mergedRaw.maxHitPoints
    }

    // Expose top-level extracted lists if present
    if (Array.isArray(sheet?.spells) && !Array.isArray(mergedRaw.spells)) mergedRaw.spells = sheet.spells
    if (Array.isArray(sheet?.classFeatures) && !Array.isArray(mergedRaw.classFeatures)) mergedRaw.classFeatures = sheet.classFeatures
    if (Array.isArray(sheet?.racialFeatures) && !Array.isArray(mergedRaw.racialFeatures)) mergedRaw.racialFeatures = sheet.racialFeatures
    // Expose spell slots so inferSpellSlotsFromRaw can find them for interactive tracking.
    if ((sheet as any)?.spell_slots && typeof (sheet as any).spell_slots === 'object' && !mergedRaw.spell_slots) {
      mergedRaw.spell_slots = (sheet as any).spell_slots
    }
    if ((sheet as any)?.spellSlots && typeof (sheet as any).spellSlots === 'object' && !mergedRaw.spellSlots) {
      mergedRaw.spellSlots = (sheet as any).spellSlots
    }
    // Expose skills so they can be displayed from whatever format the importer stored them.
    if ((sheet as any)?.skills && !mergedRaw.skills) {
      mergedRaw.skills = (sheet as any).skills
    }

    // Keep combined text available
    if (!mergedRaw.text) mergedRaw.text = sheet?.raw_text || importMeta?.extracted?.name || ''

    const raw = mergedRaw

    const hpCurrentDirect = asNumber(sheet?.hp?.current ?? sheet?.hp_current, 0)
    const hpMaxDirect = asNumber(sheet?.hp?.max ?? sheet?.hp_max, 0)
    const acDirect = asNumber(sheet?.ac, 0)

    const inferredAbilities = inferAbilitiesFromRaw(raw)
    const inferredHp = inferHpFromRaw(raw)
    const inferredAc = inferAcFromRaw(raw)
    const inferredLists = inferListsFromRaw(raw)
    const inferredFeatures = inferFeaturesFromRaw(raw)
    const inferredInventory = inferInventoryFromRaw(raw)
    const inferredMovement = inferMovementFromRaw(raw)
    const inferredDeathSaves = inferDeathSavesFromRaw(raw)
    const inferredRest = inferRestStateFromRaw(raw)
    const inferredSpellSlots = inferSpellSlotsFromRaw(raw)
    const inferredSpells = toStringListLoose(pick(raw, ['spells']))
      .concat(toStringListLoose(pick(raw, ['spellbook'])))
      .concat(toStringListLoose(pick(raw, ['knownSpells'])))

    const spellbook = (() => {
      if (Array.isArray((sheet as any)?.spellbook)) return (sheet as any).spellbook
      const rawSpellbook = pick(raw, ['spellbook'])
      if (Array.isArray(rawSpellbook)) return rawSpellbook
      return []
    })()

    return {
      hpCurrent: (hpCurrentDirect || null) ?? inferredHp.hpCurrent,
      hpMax: (hpMaxDirect || null) ?? inferredHp.hpMax,
      ac: (acDirect || null) ?? inferredAc,
      stats: {
        str: asNumber(stats?.str, 0) || inferredAbilities.str || null,
        dex: asNumber(stats?.dex, 0) || inferredAbilities.dex || null,
        con: asNumber(stats?.con, 0) || inferredAbilities.con || null,
        int: asNumber(stats?.int, 0) || inferredAbilities.int || null,
        wis: asNumber(stats?.wis, 0) || inferredAbilities.wis || null,
        cha: asNumber(stats?.cha, 0) || inferredAbilities.cha || null,
      },
      inventory: joinList(sheet?.inventory).length ? joinList(sheet?.inventory) : inferredLists.inventory,
      inventoryItems: inferredInventory,
      spells: joinList(sheet?.spells).length ? joinList(sheet?.spells) : (inferredSpells.length ? uniqNonEmpty(inferredSpells) : inferredLists.spells),
      spellbook,
      spellSlots: inferredSpellSlots,
      classFeatures: (() => {
        // Get class features as string list, filtering out section-header lines.
        const raw_cf = (sheet as any)?.classFeatures
        const items = Array.isArray(raw_cf)
          ? raw_cf.map(featureItemName).filter(Boolean)
          : inferredFeatures.classFeatures
        return uniqNonEmpty(items.filter((s: string) => !isFeatureCategoryHeader(s)))
      })(),
      racialFeatures: (() => {
        const raw_rf = (sheet as any)?.racialFeatures
        const items = Array.isArray(raw_rf)
          ? raw_rf.map(featureItemName).filter(Boolean)
          : inferredFeatures.racialFeatures
        return uniqNonEmpty(items.filter((s: string) => !isFeatureCategoryHeader(s)))
      })(),
      features: (() => {
        const raw_f = sheet?.features
        const items = Array.isArray(raw_f)
          ? raw_f.map(featureItemName).filter(Boolean)
          : (inferredFeatures.otherFeatures.length ? inferredFeatures.otherFeatures : inferredLists.features)
        return uniqNonEmpty(items.filter((s: string) => !isFeatureCategoryHeader(s)))
      })(),
      // For multiclass grouping: parse multiclass info from sheet
      multiclassGroups: (() => {
        const mc = (sheet as any)?.multiclass
        if (!Array.isArray(mc) || mc.length < 2) return null
        return mc.map((c: any) => ({
          className: asString(c?.class_name || c?.name || '').trim(),
          level: typeof c?.level === 'number' ? c.level : null,
        })).filter((c: any) => c.className)
      })(),
      // Actions / bonus actions (object with name + detail when available)
      actions: (() => {
        const rawActions = pick(raw, ['actions']) ?? pick(raw, ['attacks']) ?? pick(raw, ['specialAbilities'])
        if (Array.isArray(rawActions)) {
          return rawActions.map((a: any) => ({ name: asString(a?.name) || (typeof a === 'string' ? a : ''), detail: asString(a?.description) || asString(a?.notes) || (typeof a === 'string' ? a : '') }))
        }
        return []
      })(),
      bonusActions: (() => {
        const rawBon = pick(raw, ['bonusActions']) ?? pick(raw, ['bonus_actions']) ?? pick(raw, ['reactions'])
        if (Array.isArray(rawBon)) {
          return rawBon.map((a: any) => ({ name: asString(a?.name) || (typeof a === 'string' ? a : ''), detail: asString(a?.description) || asString(a?.notes) || (typeof a === 'string' ? a : '') }))
        }
        return []
      })(),
      skills: (() => {
        // Handle skills as: array of strings, array of {name, modifier?, proficient?},
        // or a dict {SkillName: {modifier, proficient}} (from D&D 5e extractor).
        const rawSkills = pick(raw, ['skills']) ?? pick(raw, ['skillProficiencies']) ?? pick(raw, ['skill_proficiencies'])
        if (!rawSkills) return []
        if (Array.isArray(rawSkills)) {
          return uniqNonEmpty(rawSkills.map((s: any) => {
            if (typeof s === 'string') return s.trim()
            if (s && typeof s === 'object') {
              const name = asString((s as any).name).trim()
              if (!name) return ''
              const mod = typeof (s as any).modifier === 'number' ? (s as any).modifier : (typeof (s as any).mod === 'number' ? (s as any).mod : null)
              return mod !== null ? `${name} (${mod >= 0 ? '+' : ''}${mod})` : name
            }
            return ''
          }).filter(Boolean))
        }
        if (typeof rawSkills === 'object') {
          // dict form: {SkillName: {modifier, proficient, expertise}}
          return uniqNonEmpty(
            Object.entries(rawSkills as Record<string, any>).map(([name, data]) => {
              const mod = typeof (data as any)?.modifier === 'number' ? (data as any).modifier : null
              return mod !== null ? `${name} (${mod >= 0 ? '+' : ''}${mod})` : name
            })
          )
        }
        return []
      })(),
      movement: inferredMovement,
      deathSaves: inferredDeathSaves,
      rest: inferredRest,
      raw,
    }
  }, [sheet, importMeta])

  // Expose a window hook used by InventoryList to set details (simple bridging function)
  useEffect(() => {
    ;(window as any).tt_setDetail = (title: string, text: string) => {
      setDetailTitle(title)
      setDetailText(text)
      setDetailOpen(true)
    }
    return () => { try { delete (window as any).tt_setDetail } catch {} }
  }, [])

  // Initialize localSpellSlots and preparedSpells from sheet data
  useEffect(() => {
    if (!open || !character) return
    const slots = derived.spellSlots
    // Filter out zero-max slots (e.g. a Fighter with SlotsTotal1: "0" should not
    // show an empty Level 1 row).
    setLocalSpellSlots(slots.length ? cloneJson(slots.filter((s) => (s.max ?? 0) > 0)) : [])
    const sheetPrepared: string[] = Array.isArray((sheet as any)?.preparedSpells) ? (sheet as any).preparedSpells : []
    const derivedPrepared = derived.spellbook
      .filter((s: any) => {
        const p = String(s?.prepared || '').toLowerCase()
        return ['yes', 'true', '1', 'prepared', 'y'].includes(p) || p === 'o' || p === '○'
      })
      .map((s: any) => asString(s?.name))
      .filter(Boolean)
    const combined = new Set<string>([...sheetPrepared, ...derivedPrepared])
    setPreparedSpells(combined)
  }, [open, character?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  // Bio fields derived from the sheet
  const bio = useMemo(() => {
    const story = (sheet as any)?.story && typeof (sheet as any).story === 'object' ? (sheet as any).story : {}
    const widgetVals = importMeta?.pdf_widgets?.values && typeof importMeta.pdf_widgets.values === 'object' ? importMeta.pdf_widgets.values : {}
    const alignment = asString((sheet as any)?.alignment || (widgetVals as any)?.Alignment || (widgetVals as any)?.alignment)
    const species = asString((sheet as any)?.species)
    const background = asString((sheet as any)?.background)
    const languages = (sheet as any)?.languages
    // Pathfinder 2e-specific fields
    const heritage = asString((sheet as any)?.heritage)
    const classDc = typeof (sheet as any)?.class_dc === 'number' ? (sheet as any).class_dc as number : null
    const focusPoints = (sheet as any)?.focus_points && typeof (sheet as any).focus_points === 'object' ? (sheet as any).focus_points as { max?: number; current?: number } : null
    const sheetType = asString((sheet as any)?.sheet_type)
    return {
      species,
      background,
      alignment,
      heritage,
      classDc,
      focusPoints,
      sheetType,
      personality: asString(story?.personality_traits),
      ideals: asString(story?.ideals),
      bonds: asString(story?.bonds),
      flaws: asString(story?.flaws),
      backstory: asString(story?.backstory),
      languages: toStringListLoose(languages),
      armorProficiencies: toStringListLoose((sheet as any)?.armor_proficiencies),
      weaponProficiencies: toStringListLoose((sheet as any)?.weapon_proficiencies),
      toolProficiencies: toStringListLoose((sheet as any)?.tool_proficiencies),
    }
  }, [sheet, importMeta])

  // Derive saving throws from ability scores + proficiency bonus
  const savingThrows = useMemo(() => {
    const profBonus = asNumber((sheet as any)?.proficiency_bonus, 0)
    const computeMod = (score: number | null) => score != null ? Math.floor((score - 10) / 2) : null
    const keys: Array<[string, string]> = [['str', 'STR'], ['dex', 'DEX'], ['con', 'CON'], ['int', 'INT'], ['wis', 'WIS'], ['cha', 'CHA']]
    const abilitiesData = (sheet as any)?.abilities && typeof (sheet as any).abilities === 'object' ? (sheet as any).abilities : {}
    return keys.map(([k, label]) => {
      const score = (derived.stats as any)[k] ?? null
      const baseMod = computeMod(score)
      // Try to read saving throw modifier directly from abilities dict (DDB import)
      const abilityEntry = abilitiesData[k]
      const saveValue = abilityEntry && typeof abilityEntry === 'object'
        ? asNumber((abilityEntry as any).saving_throw, NaN)
        : NaN
      const proficient = abilityEntry && typeof abilityEntry === 'object'
        ? Boolean((abilityEntry as any).saving_throw_proficient)
        : false
      const finalMod = Number.isFinite(saveValue)
        ? saveValue
        : baseMod != null
          ? baseMod + (proficient ? profBonus : 0)
          : null
      return { key: k, label, mod: finalMod, proficient }
    })
  }, [derived.stats, sheet])

  // Persist spell slot changes to backend (debounced)
  const persistSpellSlots = useCallback((slots: SpellSlot[]) => {
    if (!character) return
    if (slotSaveTimerRef.current) clearTimeout(slotSaveTimerRef.current)
    slotSaveTimerRef.current = setTimeout(async () => {
      try {
        const updatedSheet = { ...(character.sheet || {}), spellSlots: slots }
        await apiFetch(`/characters/${character.id}`, { method: 'PUT', body: JSON.stringify({ sheet: updatedSheet }) })
      } catch {}
    }, 800)
  }, [character])

  // Toggle a single spell slot pip (used count)
  const toggleSpellSlotPip = useCallback((level: number, pipIndex: number) => {
    setLocalSpellSlots(prev => {
      const next = prev.map(slot => {
        if (slot.level !== level) return slot
        const used = slot.used ?? 0
        const max = slot.max ?? 0
        // clicking an already-used pip below used count → un-use; clicking above → use
        const newUsed = pipIndex < used ? pipIndex : Math.min(pipIndex + 1, max)
        return { ...slot, used: newUsed }
      })
      persistSpellSlots(next)
      return next
    })
  }, [persistSpellSlots])

  // Persist prepared spells to backend (debounced)
  const preparedSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const persistPreparedSpells = useCallback((prepared: Set<string>) => {
    if (!character) return
    if (preparedSaveTimerRef.current) clearTimeout(preparedSaveTimerRef.current)
    preparedSaveTimerRef.current = setTimeout(async () => {
      try {
        const updatedSheet = { ...(character.sheet || {}), preparedSpells: Array.from(prepared) }
        await apiFetch(`/characters/${character.id}`, { method: 'PUT', body: JSON.stringify({ sheet: updatedSheet }) })
      } catch {}
    }, 800)
  }, [character])

  const togglePrepared = useCallback((spellName: string) => {
    setPreparedSpells(prev => {
      const next = new Set(prev)
      if (next.has(spellName)) next.delete(spellName)
      else next.add(spellName)
      persistPreparedSpells(next)
      return next
    })
  }, [persistPreparedSpells])

  // Drag handlers for spell tiles
  const handleSpellDragStart = useCallback((spellName: string) => {
    setDragSpell(spellName)
  }, [])

  const handleDropOnPrepared = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    if (!dragSpell) return
    setPreparedSpells(prev => {
      const next = new Set(prev)
      next.add(dragSpell)
      persistPreparedSpells(next)
      return next
    })
    setDragSpell(null)
  }, [dragSpell, persistPreparedSpells])

  const handleDropOnKnown = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    if (!dragSpell) return
    setPreparedSpells(prev => {
      const next = new Set(prev)
      next.delete(dragSpell)
      persistPreparedSpells(next)
      return next
    })
    setDragSpell(null)
  }, [dragSpell, persistPreparedSpells])


  function findDetailForFeature(name: string): string | null {
    if (!name) return null
    const lower = name.toLowerCase()
    // 1) If the sheet stored a full blob under class/racial/other features, use that
    const candidates = [ ...(sheet?.classFeatures || []), ...(sheet?.racialFeatures || []), ...(sheet?.otherFeatures || []), ...(sheet?.features || []) ]
    for (const c of candidates) {
      if (!c) continue
      const s = String(c)
      if (s.toLowerCase().includes(lower)) return s
    }
    // 2) Check pdf widget values
    try {
      const vals = importMeta?.pdf_widgets?.values || {}
      for (const v of Object.values(vals)) {
        if (!v) continue
        const s = String(v)
        if (s.toLowerCase().includes(lower)) return s
      }
    } catch {}
    // 3) Search combined raw text for the feature line + following lines
    const text = derived.raw?.text || sheet?.raw_text || ''
    if (text && typeof text === 'string') {
      const lines = text.split(/\r?\n/)
      for (let i = 0; i < lines.length; i++) {
        if (lines[i].toLowerCase().includes(lower)) {
          let out = lines[i].trim()
          for (let j = i + 1; j < Math.min(lines.length, i + 12); j++) {
            if (!lines[j].trim()) break
            out += '\n' + lines[j].trim()
            if (out.length > 1200) break
          }
          return out
        }
      }
    }
    return null
  }

  const title = character ? `${character.name} (L${character.level}${character.class_name ? ` ${character.class_name}` : ''})` : 'Character Sheet'

  const beginEdit = () => {
    setEditing(true)
    setEditSheet(cloneJson(sheet))
    setEditName(character?.name || '')
    setEditLevel(String(character?.level ?? ''))
    setEditClassName(character?.class_name || '')
  }

  const content = (
    <>
      {loading ? (
        <div className="inline-alert">Loading...</div>
      ) : !character ? (
        <div className="inline-alert inline-alert-error">No character selected.</div>
      ) : (
        <div className="stack">
          <div className="row-wrap tt-sheet-top">
            <div className="muted">
              {source ? `Source: ${source}` : "Source: manual"}
              {importMeta?.imported_at ? ` • Imported: ${asString(importMeta.imported_at)}` : ""}
            </div>
            <button className="btn btn-quiet btn-sm" type="button" onClick={() => setShowRaw((v) => !v)}>
              {showRaw ? "Hide raw" : "Show raw"}
            </button>
          </div>

          {/* Tab navigation */}
          <div className="tt-sheet-tabs" role="tablist">
            {(["overview", "bio", "spells", "features"] as SheetTab[]).map((tab) => (
              <button
                key={tab}
                role="tab"
                aria-selected={activeTab === tab}
                className={`tt-sheet-tab ${activeTab === tab ? "tt-sheet-tab--active" : ""}`}
                onClick={() => setActiveTab(tab)}
              >
                {tab.charAt(0).toUpperCase() + tab.slice(1)}
              </button>
            ))}
          </div>

          {/* OVERVIEW TAB */}
          {activeTab === "overview" ? (
            <>
              {bio.sheetType === "ship" ? (
                <div className="inline-alert" style={{ background: "rgba(251,191,36,0.15)", borderColor: "#fbbf24", color: "#fbbf24" }}>
                  ⚓ Ship/Vehicle Sheet — This sheet represents a vessel, not a character. Fields are stored as-is; consider adding it as a campaign document for gameplay reference.
                </div>
              ) : null}
              {ddbUrl ? (
                <div className="card tt-sheet-card">
                  <div className="muted" style={{ marginBottom: 6 }}>D&D Beyond</div>
                  <div className="row-wrap" style={{ justifyContent: "space-between", alignItems: "center" }}>
                    <div className="input input-mono tt-sheet-ddb-url">{ddbUrl}</div>
                    <a className="btn btn-sm btn-secondary" href={ddbUrl} target="_blank" rel="noreferrer">Open</a>
                  </div>
                  <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
                    We do not scrape DDB links; this is a reference URL.
                  </div>
                </div>
              ) : null}

              {pdfMeta ? (
                <div className="card tt-sheet-card">
                  <div className="muted" style={{ marginBottom: 6 }}>PDF extraction</div>
                  <div className="row-wrap" style={{ gap: 12 }}>
                    <div><strong>Widgets:</strong> {pdfMeta.widgetCount ?? "—"}</div>
                    <div><strong>Text chars:</strong> {pdfMeta.rawTextLen ?? "—"}</div>
                  </div>
                  {(pdfMeta.extracted?.name || pdfMeta.extracted?.level || pdfMeta.extracted?.class_name) ? (
                    <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
                      Extracted: {pdfMeta.extracted?.name ? `Name "${pdfMeta.extracted.name}"` : "Name —"} ·
                      {pdfMeta.extracted?.level ? ` Level ${pdfMeta.extracted.level}` : " Level —"} ·
                      {pdfMeta.extracted?.class_name ? ` Class ${pdfMeta.extracted.class_name}` : " Class —"}
                    </div>
                  ) : null}
                  {importMeta?.document_id && importMeta?.document_session_id ? (
                    <div style={{ marginTop: 10 }}>
                      <div className="muted" style={{ marginBottom: 6 }}>Original PDF</div>
                      <div style={{ height: 420, border: "1px solid rgba(255,255,255,0.06)" }}>
                        <iframe
                          title="character-pdf"
                          src={`${API_BASE}/documents/${importMeta.document_session_id}/${importMeta.document_id}/raw`}
                          style={{ width: "100%", height: "100%", border: 0 }}
                        />
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : null}

              <div className="tt-sheet-grid">
                <div className="card tt-sheet-card">
                  <div className="muted" style={{ marginBottom: 6 }}>Overview</div>
                  <div><strong>Name:</strong> {character.name}</div>
                  <div><strong>Level:</strong> {character.level}</div>
                  <div><strong>Class:</strong> {character.class_name || "—"}</div>
                  {bio.species ? <div><strong>{bio.heritage ? 'Ancestry' : 'Species'}:</strong> {bio.species}</div> : null}
                  {bio.heritage ? <div><strong>Heritage:</strong> {bio.heritage}</div> : null}
                  {bio.background ? <div><strong>Background:</strong> {bio.background}</div> : null}
                  {bio.alignment ? <div><strong>Alignment:</strong> {bio.alignment}</div> : null}
                </div>
                <div className="card tt-sheet-card">
                  <div className="muted" style={{ marginBottom: 6 }}>Combat</div>
                  <div><strong>HP:</strong> {derived.hpCurrent ?? "—"} / {derived.hpMax ?? "—"}</div>
                  <div><strong>AC:</strong> {derived.ac ?? "—"}</div>
                  {bio.classDc != null ? <div><strong>Class DC:</strong> {bio.classDc}</div> : null}
                  {bio.focusPoints != null ? (
                    <div><strong>Focus Points:</strong> {bio.focusPoints.current ?? "—"} / {bio.focusPoints.max ?? "—"}</div>
                  ) : null}
                </div>
                <div className="card tt-sheet-card">
                  <div className="muted" style={{ marginBottom: 6 }}>Status</div>
                  <div><strong>Death Saves:</strong> {derived.deathSaves.successes ?? "—"} ✓ / {derived.deathSaves.failures ?? "—"} ✗</div>
                  <div><strong>Hit Dice:</strong> {derived.rest.hitDiceUsed ?? "—"} / {derived.rest.hitDiceTotal ?? "—"}</div>
                  <div><strong>Inspiration:</strong> {derived.rest.inspiration === null ? "—" : derived.rest.inspiration ? "Yes" : "No"}</div>
                  <div><strong>Exhaustion:</strong> {derived.rest.exhaustion ?? "—"}</div>
                </div>
                <div className="card tt-sheet-card">
                  <div className="muted" style={{ marginBottom: 6 }}>Movement</div>
                  <div><strong>Walk:</strong> {derived.movement.walk ?? "—"} ft</div>
                  <div><strong>Fly:</strong> {derived.movement.fly ?? "—"} ft</div>
                  <div><strong>Swim:</strong> {derived.movement.swim ?? "—"} ft</div>
                  <div><strong>Climb:</strong> {derived.movement.climb ?? "—"} ft</div>
                  <div><strong>Burrow:</strong> {derived.movement.burrow ?? "—"} ft</div>
                </div>
              </div>

              <div className="card tt-sheet-abilities">
                <div className="muted" style={{ marginBottom: 6 }}>Ability scores</div>
                <div className="tt-abilities-grid">
                  {(["str","dex","con","int","wis","cha"] as const).map((k) => (
                    <div key={k} className="input input-mono tt-ability">
                      <div className="tt-ability-label">{k.toUpperCase()}</div>
                      <div className="tt-ability-value">{(derived.stats as any)[k] ?? "—"}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Saving throws */}
              <div className="card tt-sheet-card">
                <div className="muted" style={{ marginBottom: 6 }}>Saving Throws</div>
                <div className="tt-saving-throws-grid">
                  {savingThrows.map(({ key, label, mod, proficient }) => (
                    <div key={key} className={`tt-save-item ${proficient ? "tt-save-item--proficient" : ""}`}>
                      <span className="tt-save-pip">{proficient ? "●" : "○"}</span>
                      <span className="tt-save-label">{label}</span>
                      <span className="tt-save-mod">{mod != null ? (mod >= 0 ? `+${mod}` : String(mod)) : "—"}</span>
                    </div>
                  ))}
                </div>
              </div>

              {derived.inventory.length ? <ListPreview title="Inventory" items={derived.inventory} /> : null}
              {derived.inventoryItems.length ? <InventoryList items={derived.inventoryItems} /> : null}

              {derived.actions && derived.actions.length ? (
                <div className="card tt-sheet-card">
                  <div className="muted" style={{ marginBottom: 6 }}>Actions</div>
                  <ul style={{ margin: 0, paddingLeft: 18 }}>
                    {derived.actions.map((a: any, idx: number) => (
                      <li key={`action-${idx}`}>
                        <button className="btn btn-ghost" style={{ padding: 0, textAlign: "left" }} onClick={() => { setDetailTitle(a.name || "Action"); setDetailText(a.detail || ""); setDetailOpen(true) }}>{a.name}</button>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {derived.bonusActions && derived.bonusActions.length ? (
                <div className="card tt-sheet-card">
                  <div className="muted" style={{ marginBottom: 6 }}>Bonus Actions</div>
                  <ul style={{ margin: 0, paddingLeft: 18 }}>
                    {derived.bonusActions.map((a: any, idx: number) => (
                      <li key={`baction-${idx}`}>
                        <button className="btn btn-ghost" style={{ padding: 0, textAlign: "left" }} onClick={() => { setDetailTitle(a.name || "Bonus Action"); setDetailText(a.detail || ""); setDetailOpen(true) }}>{a.name}</button>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {(() => {
                // Prefer the structured skill objects (with proficiency data) stored in
                // sheet.skills over the pre-flattened derived.skills string list.
                const rawSkillList: any[] = Array.isArray((sheet as any)?.skills) ? (sheet as any).skills : []
                const hasObjects = rawSkillList.some(
                  (s) => s && typeof s === 'object' && 'name' in s
                )
                if (hasObjects) {
                  return (
                    <div className="card tt-sheet-card">
                      <div className="muted" style={{ marginBottom: 6 }}>Skills</div>
                      <div className="tt-skills-grid">
                        {rawSkillList.map((s: any) => {
                          const name = typeof s === 'string' ? s : asString((s as any)?.name)
                          if (!name) return null
                          const mod =
                            typeof (s as any)?.modifier === 'number'
                              ? (s as any).modifier
                              : typeof (s as any)?.mod === 'number'
                              ? (s as any).mod
                              : null
                          const proficient = (s as any)?.proficient === true || (s as any)?.expertise === true
                          return (
                            <div key={name} className={`tt-skill-item ${proficient ? 'tt-skill-item--proficient' : ''}`}>
                              <span className="tt-skill-pip">{proficient ? '●' : '○'}</span>
                              <span className="tt-skill-name">{name}</span>
                              <span className="tt-skill-mod">
                                {mod !== null ? (mod >= 0 ? `+${mod}` : String(mod)) : '—'}
                              </span>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )
                }
                if (derived.skills && derived.skills.length) {
                  return (
                    <div className="card tt-sheet-card">
                      <div className="muted" style={{ marginBottom: 6 }}>Skills</div>
                      <ul style={{ margin: 0, paddingLeft: 18 }}>
                        {derived.skills.map((s) => <li key={s}>{s}</li>)}
                      </ul>
                    </div>
                  )
                }
                return null
              })()}

              {showRaw ? (
                <div className="card tt-sheet-card">
                  <div className="muted" style={{ marginBottom: 6 }}>Raw sheet JSON</div>
                  <pre className="code-block tt-sheet-raw">
                    {JSON.stringify(sheet, null, 2)}
                  </pre>
                </div>
              ) : null}
            </>
          ) : null}

          {/* BIO TAB */}
          {activeTab === "bio" ? (
            <>
              <div className="tt-sheet-grid">
                <div className="card tt-sheet-card">
                  <div className="muted" style={{ marginBottom: 6 }}>Identity</div>
                  <div><strong>{bio.heritage ? 'Ancestry' : 'Species'}:</strong> {bio.species || "—"}</div>
                  {bio.heritage ? <div><strong>Heritage:</strong> {bio.heritage}</div> : null}
                  <div><strong>Background:</strong> {bio.background || "—"}</div>
                  <div><strong>Alignment:</strong> {bio.alignment || "—"}</div>
                </div>
                {bio.languages.length ? (
                  <div className="card tt-sheet-card">
                    <div className="muted" style={{ marginBottom: 6 }}>Languages</div>
                    <ul style={{ margin: 0, paddingLeft: 18 }}>
                      {bio.languages.map((l) => <li key={l}>{l}</li>)}
                    </ul>
                  </div>
                ) : null}
              </div>

              {(bio.personality || bio.ideals || bio.bonds || bio.flaws) ? (
                <div className="tt-sheet-grid">
                  {bio.personality ? (
                    <div className="card tt-sheet-card">
                      <div className="muted" style={{ marginBottom: 4 }}>Personality Traits</div>
                      <div style={{ whiteSpace: "pre-wrap", fontSize: 13 }}>{bio.personality}</div>
                    </div>
                  ) : null}
                  {bio.ideals ? (
                    <div className="card tt-sheet-card">
                      <div className="muted" style={{ marginBottom: 4 }}>Ideals</div>
                      <div style={{ whiteSpace: "pre-wrap", fontSize: 13 }}>{bio.ideals}</div>
                    </div>
                  ) : null}
                  {bio.bonds ? (
                    <div className="card tt-sheet-card">
                      <div className="muted" style={{ marginBottom: 4 }}>Bonds</div>
                      <div style={{ whiteSpace: "pre-wrap", fontSize: 13 }}>{bio.bonds}</div>
                    </div>
                  ) : null}
                  {bio.flaws ? (
                    <div className="card tt-sheet-card">
                      <div className="muted" style={{ marginBottom: 4 }}>Flaws</div>
                      <div style={{ whiteSpace: "pre-wrap", fontSize: 13 }}>{bio.flaws}</div>
                    </div>
                  ) : null}
                </div>
              ) : null}

              {bio.backstory ? (
                <div className="card tt-sheet-card">
                  <div className="muted" style={{ marginBottom: 4 }}>Backstory</div>
                  <div style={{ whiteSpace: "pre-wrap", fontSize: 13 }}>{bio.backstory}</div>
                </div>
              ) : null}

              {(bio.armorProficiencies.length || bio.weaponProficiencies.length || bio.toolProficiencies.length) ? (
                <div className="tt-sheet-grid">
                  {bio.armorProficiencies.length ? (
                    <div className="card tt-sheet-card">
                      <div className="muted" style={{ marginBottom: 4 }}>Armor Proficiencies</div>
                      <ul style={{ margin: 0, paddingLeft: 18 }}>
                        {bio.armorProficiencies.map((p) => <li key={p}>{p}</li>)}
                      </ul>
                    </div>
                  ) : null}
                  {bio.weaponProficiencies.length ? (
                    <div className="card tt-sheet-card">
                      <div className="muted" style={{ marginBottom: 4 }}>Weapon Proficiencies</div>
                      <ul style={{ margin: 0, paddingLeft: 18 }}>
                        {bio.weaponProficiencies.map((p) => <li key={p}>{p}</li>)}
                      </ul>
                    </div>
                  ) : null}
                  {bio.toolProficiencies.length ? (
                    <div className="card tt-sheet-card">
                      <div className="muted" style={{ marginBottom: 4 }}>Tool Proficiencies</div>
                      <ul style={{ margin: 0, paddingLeft: 18 }}>
                        {bio.toolProficiencies.map((p) => <li key={p}>{p}</li>)}
                      </ul>
                    </div>
                  ) : null}
                </div>
              ) : null}

              {!bio.species && !bio.background && !bio.personality && !bio.backstory && !bio.languages.length ? (
                <div className="muted" style={{ padding: 12 }}>No biography data available. Import a character sheet with filled-in fields to populate this section.</div>
              ) : null}
            </>
          ) : null}

          {/* SPELLS TAB */}
          {activeTab === "spells" ? (
            <>
              {localSpellSlots.length ? (
                <div className="card tt-sheet-card">
                  <div className="muted" style={{ marginBottom: 8 }}>Spell Slots <span style={{ fontSize: 11 }}>(click to mark used/unused)</span></div>
                  <div className="tt-spell-slots">
                    {localSpellSlots.map((slot) => {
                      const max = slot.max ?? 0
                      const used = slot.used ?? 0
                      return (
                        <div key={slot.level} className="tt-spell-slot-row">
                          <span className="tt-spell-slot-label">L{slot.level}</span>
                          <div className="tt-spell-slot-pips">
                            {Array.from({ length: max }).map((_, i) => (
                              <button
                                key={i}
                                type="button"
                                aria-label={`Level ${slot.level} slot ${i + 1} — ${i < used ? "used" : "available"}`}
                                className={`tt-spell-slot-pip ${i < used ? "tt-spell-slot-pip--used" : ""}`}
                                onClick={() => toggleSpellSlotPip(slot.level, i)}
                              />
                            ))}
                          </div>
                          <span className="tt-spell-slot-count">{used}/{max}</span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              ) : null}

              {(derived.spells.length || derived.spellbook.length) ? (
                <div className="tt-spell-columns">
                  <div
                    className="tt-spell-col"
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={handleDropOnKnown}
                  >
                    <div className="tt-spell-col-header">Known Spells</div>
                    <div className="tt-spell-tiles">
                      {(derived.spellbook.length ? derived.spellbook.map((s: any) => asString(s?.name)).filter(Boolean) : derived.spells).map((name: string) => {
                        const isPrepared = preparedSpells.has(name)
                        return (
                          <div
                            key={name}
                            draggable
                            onDragStart={() => handleSpellDragStart(name)}
                            className={`tt-spell-tile ${isPrepared ? "tt-spell-tile--grayed" : ""}`}
                            title={isPrepared ? `${name} (prepared)` : name}
                          >
                            <span className="tt-spell-tile-name">{name}</span>
                            <button
                              type="button"
                              className="tt-spell-tile-prep-btn"
                              aria-label={isPrepared ? `Remove ${name} from prepared` : `Prepare ${name}`}
                              onClick={() => togglePrepared(name)}
                            >
                              {isPrepared ? "check" : "+"}
                            </button>
                          </div>
                        )
                      })}
                    </div>
                  </div>

                  <div
                    className="tt-spell-col tt-spell-col--prepared"
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={handleDropOnPrepared}
                  >
                    <div className="tt-spell-col-header">Prepared Spells</div>
                    <div className="tt-spell-tiles">
                      {Array.from(preparedSpells).map((name) => (
                        <div
                          key={name}
                          draggable
                          onDragStart={() => handleSpellDragStart(name)}
                          className="tt-spell-tile tt-spell-tile--prepared"
                          title={name}
                        >
                          <span className="tt-spell-tile-name">{name}</span>
                          <button
                            type="button"
                            className="tt-spell-tile-prep-btn"
                            aria-label={`Remove ${name} from prepared`}
                            onClick={() => togglePrepared(name)}
                          >
                            x
                          </button>
                        </div>
                      ))}
                      {preparedSpells.size === 0 ? (
                        <div className="tt-spell-col-empty">Drag spells here to prepare them</div>
                      ) : null}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="muted" style={{ padding: 12 }}>No spell data available for this character.</div>
              )}

              {derived.spellbook.length ? (
                <div className="card tt-sheet-card" style={{ marginTop: 12 }}>
                  <div className="muted" style={{ marginBottom: 6 }}>Spellbook Details</div>
                  <div style={{ maxHeight: 280, overflow: "auto" }}>
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
                          derived.spellbook.slice(0, 120).forEach((spell: any, idx: number) => {
                            const header = (spell?.header || spell?.slot_header || "").trim()
                            if (header && header !== lastHeader) {
                              lastHeader = header
                              rows.push({ type: "header", label: header, key: `header-${idx}` })
                            }
                            rows.push({ type: "spell", spell, key: `spellbook-${idx}` })
                          })
                          return rows.map((row) => {
                            if (row.type === "header") {
                              return (
                                <tr key={row.key} className="spellbook-header-row">
                                  <td colSpan={10}>{row.label}</td>
                                </tr>
                              )
                            }
                            const spell = row.spell
                            const isPrepared = preparedSpells.has(asString(spell?.name))
                            return (
                              <tr key={row.key} className={isPrepared ? "spellbook-row--prepared" : ""}>
                                <td className="spellbook-prep">{isPrepared ? "●" : "○"}</td>
                                <td className="spellbook-name">{spell?.name || "—"}</td>
                                <td>{spell?.source || "—"}</td>
                                <td>{spell?.save_hit || "—"}</td>
                                <td>{spell?.time || "—"}</td>
                                <td>{spell?.range || "—"}</td>
                                <td>{spell?.components || "—"}</td>
                                <td>{spell?.duration || "—"}</td>
                                <td>{spell?.page || "—"}</td>
                                <td>{spell?.notes || "—"}</td>
                              </tr>
                            )
                          })
                        })()}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : null}
            </>
          ) : null}

          {/* FEATURES TAB */}
          {activeTab === "features" ? (
            <>
              {derived.classFeatures.length ? (() => {
                // For multiclass characters with 2+ classes, try to split class features
                // by class name using simple prefix matching.
                const mc = derived.multiclassGroups
                const onItemClick = (it: string) => { const d = findDetailForFeature(it); setDetailTitle(it); setDetailText(d || it); setDetailOpen(true) }
                if (mc && mc.length >= 2) {
                  const groups: Array<{ label: string; items: string[] }> = []
                  const assigned = new Set<string>()
                  for (const cls of mc) {
                    const cname = cls.className.toLowerCase()
                    const matching = derived.classFeatures.filter((f: string) => {
                      if (assigned.has(f)) return false
                      // Match if the feature name contains the class name, or a class-specific keyword
                      return f.toLowerCase().includes(cname)
                    })
                    if (matching.length) {
                      matching.forEach((f: string) => assigned.add(f))
                      const label = cls.level ? `${cls.className} Features (Level ${cls.level})` : `${cls.className} Features`
                      groups.push({ label, items: matching })
                    }
                  }
                  // Remaining unassigned features go to a generic group
                  const remaining = derived.classFeatures.filter((f: string) => !assigned.has(f))
                  if (remaining.length) groups.push({ label: 'Class Features', items: remaining })
                  // If grouping worked, show groups; otherwise show flat list
                  if (groups.length > 1) {
                    return <>{groups.map((g) => <ListPreview key={g.label} title={g.label} items={g.items} onItemClick={onItemClick} />)}</>
                  }
                }
                return <ListPreview title="Class Features" items={derived.classFeatures} onItemClick={onItemClick} />
              })() : null}
              {derived.racialFeatures.length ? <ListPreview title="Racial / Species Features" items={derived.racialFeatures} onItemClick={(it) => { const d = findDetailForFeature(it); setDetailTitle(it); setDetailText(d || it); setDetailOpen(true) }} /> : null}
              {!derived.classFeatures.length && !derived.racialFeatures.length && derived.features.length ? (
                <ListPreview title="Features" items={derived.features} onItemClick={(it) => { const d = findDetailForFeature(it); setDetailTitle(it); setDetailText(d || it); setDetailOpen(true) }} />
              ) : null}
              {!derived.classFeatures.length && !derived.racialFeatures.length && !derived.features.length ? (
                <div className="muted" style={{ padding: 12 }}>No feature data available for this character.</div>
              ) : null}
            </>
          ) : null}

          {/* Edit panel */}
          {!editing ? (
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
              <button className="btn btn-quiet" type="button" onClick={beginEdit}>
                Edit character
              </button>
            </div>
          ) : null}

          {editing ? (
            <div className="card card-pad stack" style={{ background: "rgba(255,255,255,0.02)" }}>
              <div style={{ fontWeight: 700 }}>Edit character</div>
              <div className="row-wrap" style={{ gap: 10 }}>
                <div className="stack" style={{ gap: 6, minWidth: 180 }}>
                  <label className="muted">Name</label>
                  <input className="input" value={editName} onChange={(e) => setEditName(e.target.value)} />
                </div>
                <div className="stack" style={{ gap: 6, minWidth: 120 }}>
                  <label className="muted">Level</label>
                  <input className="input input-mono" type="number" min={1} max={20} value={editLevel} onChange={(e) => setEditLevel(e.target.value)} />
                </div>
                <div className="stack" style={{ gap: 6, minWidth: 180 }}>
                  <label className="muted">Class</label>
                  <input className="input" value={editClassName} onChange={(e) => setEditClassName(e.target.value)} />
                </div>
              </div>
              <div className="row-wrap" style={{ gap: 10 }}>
                {(["str","dex","con","int","wis","cha"] as const).map((k) => (
                  <div key={k} className="stack" style={{ gap: 6 }}>
                    <label className="muted">{k.toUpperCase()}</label>
                    <input className="input input-mono" value={String(editSheet?.stats?.[k] ?? "")} onChange={(e) => { setEditSheet((s: any)=>({ ...s, stats: { ...(s?.stats||{}), [k]: parseInt(e.target.value || "0",10) }})) }} />
                  </div>
                ))}
                <div className="stack" style={{ gap: 6 }}>
                  <label className="muted">AC</label>
                  <input className="input input-mono" value={String(editSheet?.ac ?? "")} onChange={(e)=>setEditSheet((s:any)=>({ ...s, ac: Number(e.target.value || 0)}))} />
                </div>
                <div className="stack" style={{ gap: 6 }}>
                  <label className="muted">HP max</label>
                  <input className="input input-mono" value={String(editSheet?.hp?.max ?? "")} onChange={(e)=>setEditSheet((s:any)=>({ ...s, hp: { ...(s?.hp||{}), max: Number(e.target.value || 0)}}))} />
                </div>
                <div className="stack" style={{ gap: 6 }}>
                  <label className="muted">HP current</label>
                  <input className="input input-mono" value={String(editSheet?.hp?.current ?? "")} onChange={(e)=>setEditSheet((s:any)=>({ ...s, hp: { ...(s?.hp||{}), current: Number(e.target.value || 0)}}))} />
                </div>
              </div>
              <div style={{ marginTop: 8 }}>
                <label className="muted">Features (one per line)</label>
                <textarea className="input" rows={6} value={Array.isArray(editSheet?.features) ? editSheet.features.join("\n") : String(editSheet?.features || "")} onChange={(e)=>setEditSheet((s:any)=>({ ...s, features: e.target.value.split("\n").map((r:string)=>r.trim()).filter(Boolean)}))} />
              </div>
              <div className="row-wrap" style={{ justifyContent: "flex-end", gap: 8 }}>
                <button className="btn btn-secondary" type="button" onClick={()=>{ setEditing(false); setEditSheet(null); }} disabled={saveBusy}>Cancel</button>
                <button className="btn" type="button" onClick={async ()=>{
                  if(!character) return
                  setSaveBusy(true)
                  try{
                    const parsedLevel = parseInt(editLevel.trim(), 10)
                    const safeLevel = Number.isFinite(parsedLevel) ? Math.max(1, Math.min(20, parsedLevel)) : character.level
                    const payload: any = {
                      sheet: editSheet,
                      name: editName.trim() || character.name,
                      level: safeLevel,
                      class_name: editClassName.trim() || null,
                    }
                    const res = await apiFetch(`/characters/${character.id}`, { method: "PUT", body: JSON.stringify(payload) })
                    if(!res.ok){ const err = await res.json().catch(()=>({})); alert(err?.detail || "Failed to save"); return }
                    setEditing(false)
                    setEditSheet(null)
                    if (onSaved) await onSaved()
                    onClose()
                  }catch(e:any){ alert(e?.message||"Network error") }finally{ setSaveBusy(false) }
                }}>Save</button>
              </div>
            </div>
          ) : null}

          <Modal open={detailOpen} title={detailTitle || "Detail"} onClose={() => setDetailOpen(false)}>
            <div className="stack" style={{ gap: 8 }}>
              <div style={{ whiteSpace: "pre-wrap", fontSize: 14 }}>{detailText || "No additional details available."}</div>
              {character?.sheet?.references && detailTitle ? (
                <div style={{ marginTop: 8 }}>
                  <div className="muted" style={{ marginBottom: 6 }}>References</div>
                  {(() => {
                    const refsAll = character.sheet.references || {}
                    const featRefs = refsAll.features?.[detailTitle] || refsAll.spells?.[detailTitle] || []
                    if (!Array.isArray(featRefs) || featRefs.length === 0) return <div className="muted">No matches in uploaded references.</div>
                    return (
                      <ul style={{ margin: 0, paddingLeft: 18 }}>
                        {featRefs.map((r: any, idx: number) => (
                          <li key={`ref-${idx}`} style={{ marginBottom: 6 }}>
                            <div style={{ fontSize: 13 }}><strong>{String(r.source_id)}</strong> - Page {String(r.page)}</div>
                            <div className="muted" style={{ fontSize: 13, marginBottom: 6 }}>{r.snippet}</div>
                            <div style={{ display: "flex", gap: 8 }}>
                              <a className="btn btn-quiet btn-sm" target="_blank" rel="noreferrer" href={`${API_BASE}/references/${encodeURIComponent(String(r.source_id))}/raw#page=${encodeURIComponent(String(r.page))}`}>Open source</a>
                            </div>
                          </li>
                        ))}
                      </ul>
                    )
                  })()}
                </div>
              ) : null}
              <div style={{ display: "flex", justifyContent: "flex-end" }}>
                <button className="btn btn-secondary" type="button" onClick={() => setDetailOpen(false)}>Close</button>
              </div>
            </div>
          </Modal>

          {!ddbUrl && !Object.keys(derived.raw || {}).length ? (
            <div className="inline-alert" style={{ marginTop: 6 }}>
              This character was created from a link and does not have a parsed sheet yet. If you want full stats/spells,
              import a JSON export.
            </div>
          ) : null}
        </div>
      )}
    </>
  )

  if (embedded) {
    return (
      <div className="card card-pad">
        <div style={{ fontWeight: 700, marginBottom: 8 }}>{title}</div>
        {content}
      </div>
    )
  }

  return (
    <Modal open={open} title={title} onClose={onClose}>
      {content}
    </Modal>
  )
}
