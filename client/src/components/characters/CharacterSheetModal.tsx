import React, { useEffect, useMemo, useState } from 'react'

import Modal from '../ui/Modal'
import { apiFetch, API_BASE } from '../../api'

import './CharacterSheetModal.css'

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
  const shown = items.slice(0, limit)
  const remaining = items.length - shown.length
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
        <details style={{ marginTop: 8 }}>
          <summary className="muted" style={{ cursor: 'pointer' }}>Show all ({items.length})</summary>
          <ul style={{ marginTop: 8, marginBottom: 0, paddingLeft: 18 }}>
            {items.slice(limit).map((item) => <li key={item}>{item}</li>)}
          </ul>
        </details>
      ) : null}
    </div>
  )
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
              const details = item.notes || `${item.name}${item.quantity ? ` x${item.quantity}` : ''}${item.type ? ` • ${item.type}` : ''}${item.weight ? ` • ${item.weight} lb` : ''}${item.cost ? ` • ${item.cost}` : ''}`
              ;(window as any).tt_setDetail && (window as any).tt_setDetail(item.name, details)
            }}>{item.name}</button>
            {item.quantity ? ` x${item.quantity}` : ''}
            {item.type ? <span className="muted"> • {item.type}</span> : null}
            {item.weight ? <span className="muted"> • {item.weight} lb</span> : null}
            {item.cost ? <span className="muted"> • {item.cost}</span> : null}
            {item.notes ? <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>{item.notes}</div> : null}
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function CharacterSheetModal({ open, character, loading = false, onClose, onSaved }: Props) {
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

  useEffect(() => {
    if (!open) return
    // Default to the organized view every time you open a sheet.
    setShowRaw(false)
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
      spellSlots: inferredSpellSlots,
      classFeatures: joinList((sheet as any)?.classFeatures).length ? joinList((sheet as any)?.classFeatures) : inferredFeatures.classFeatures,
      racialFeatures: joinList((sheet as any)?.racialFeatures).length ? joinList((sheet as any)?.racialFeatures) : inferredFeatures.racialFeatures,
      features: joinList(sheet?.features).length ? joinList(sheet?.features) : inferredFeatures.otherFeatures.length ? inferredFeatures.otherFeatures : inferredLists.features,
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
      skills: uniqNonEmpty([ ...toStringListLoose(pick(raw, ['skills'])), ...toStringListLoose(pick(raw, ['skillProficiencies'])), ...toStringListLoose(pick(raw, ['skill_proficiencies'])) ]),
      movement: inferredMovement,
      deathSaves: inferredDeathSaves,
      rest: inferredRest,
      raw,
    }
  }, [sheet])

  // Expose a window hook used by InventoryList to set details (simple bridging function)
  useEffect(() => {
    ;(window as any).tt_setDetail = (title: string, text: string) => {
      setDetailTitle(title)
      setDetailText(text)
      setDetailOpen(true)
    }
    return () => { try { delete (window as any).tt_setDetail } catch {} }
  }, [])

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

  return (
    <Modal open={open} title={title} onClose={onClose}>
      {loading ? (
        <div className="inline-alert">Loading…</div>
      ) : !character ? (
        <div className="inline-alert inline-alert-error">No character selected.</div>
      ) : (
        <div className="stack">
          <div className="row-wrap tt-sheet-top">
            <div className="muted">
              {source ? `Source: ${source}` : 'Source: manual'}
              {importMeta?.imported_at ? ` • Imported: ${asString(importMeta.imported_at)}` : ''}
            </div>
            <button className="btn btn-quiet btn-sm" type="button" onClick={() => setShowRaw((v) => !v)}>
              {showRaw ? 'Hide raw' : 'Show raw'}
            </button>
          </div>

          {ddbUrl ? (
            <div className="card tt-sheet-card">
              <div className="muted" style={{ marginBottom: 6 }}>D&D Beyond</div>
              <div className="row-wrap" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
                <div className="input input-mono tt-sheet-ddb-url">{ddbUrl}</div>
                <a className="btn btn-sm btn-secondary" href={ddbUrl} target="_blank" rel="noreferrer">Open</a>
              </div>
              <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
                We don’t scrape DDB links; this is a reference URL.
              </div>
            </div>
          ) : null}

          {pdfMeta ? (
            <div className="card tt-sheet-card">
              <div className="muted" style={{ marginBottom: 6 }}>PDF extraction</div>
              <div className="row-wrap" style={{ gap: 12 }}>
                <div><strong>Widgets:</strong> {pdfMeta.widgetCount ?? '—'}</div>
                <div><strong>Text chars:</strong> {pdfMeta.rawTextLen ?? '—'}</div>
              </div>
              {(pdfMeta.extracted?.name || pdfMeta.extracted?.level || pdfMeta.extracted?.class_name) ? (
                <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
                  Extracted: {pdfMeta.extracted?.name ? `Name “${pdfMeta.extracted.name}”` : 'Name —'} •
                  {pdfMeta.extracted?.level ? ` Level ${pdfMeta.extracted.level}` : ' Level —'} •
                  {pdfMeta.extracted?.class_name ? ` Class ${pdfMeta.extracted.class_name}` : ' Class —'}
                </div>
              ) : null}
              {(pdfMeta.overrides?.name || pdfMeta.overrides?.level || pdfMeta.overrides?.class_name) ? (
                <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                  Overrides: {pdfMeta.overrides?.name ? `Name “${pdfMeta.overrides.name}”` : 'Name —'} •
                  {pdfMeta.overrides?.level ? ` Level ${pdfMeta.overrides.level}` : ' Level —'} •
                  {pdfMeta.overrides?.class_name ? ` Class ${pdfMeta.overrides.class_name}` : ' Class —'}
                </div>
              ) : null}

              {/* If the import referenced a stored document, render an embedded viewer */}
              {importMeta?.document_id && importMeta?.document_session_id ? (
                <div style={{ marginTop: 10 }}>
                  <div className="muted" style={{ marginBottom: 6 }}>Original PDF</div>
                  <div style={{ height: 420, border: '1px solid rgba(255,255,255,0.06)' }}>
                    <iframe
                      title="character-pdf"
                      src={`${API_BASE}/documents/${importMeta.document_session_id}/${importMeta.document_id}/raw`}
                      style={{ width: '100%', height: '100%', border: 0 }}
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
              <div><strong>Class:</strong> {character.class_name || '—'}</div>
            </div>
            <div className="card tt-sheet-card">
              <div className="muted" style={{ marginBottom: 6 }}>Combat</div>
              <div><strong>HP:</strong> {derived.hpCurrent ?? '—'} / {derived.hpMax ?? '—'}</div>
              <div><strong>AC:</strong> {derived.ac ?? '—'}</div>
            </div>
            <div className="card tt-sheet-card">
              <div className="muted" style={{ marginBottom: 6 }}>Status</div>
              <div><strong>Death Saves:</strong> {derived.deathSaves.successes ?? '—'} ✓ / {derived.deathSaves.failures ?? '—'} ✗</div>
              <div><strong>Hit Dice:</strong> {derived.rest.hitDiceUsed ?? '—'} / {derived.rest.hitDiceTotal ?? '—'}</div>
              <div><strong>Inspiration:</strong> {derived.rest.inspiration === null ? '—' : derived.rest.inspiration ? 'Yes' : 'No'}</div>
              <div><strong>Exhaustion:</strong> {derived.rest.exhaustion ?? '—'}</div>
            </div>
            <div className="card tt-sheet-card">
              <div className="muted" style={{ marginBottom: 6 }}>Movement</div>
              <div><strong>Walk:</strong> {derived.movement.walk ?? '—'} ft</div>
              <div><strong>Fly:</strong> {derived.movement.fly ?? '—'} ft</div>
              <div><strong>Swim:</strong> {derived.movement.swim ?? '—'} ft</div>
              <div><strong>Climb:</strong> {derived.movement.climb ?? '—'} ft</div>
              <div><strong>Burrow:</strong> {derived.movement.burrow ?? '—'} ft</div>
            </div>
          </div>

          <div className="card tt-sheet-abilities">
            <div className="muted" style={{ marginBottom: 6 }}>Ability scores</div>
            <div className="tt-abilities-grid">
              {(['str','dex','con','int','wis','cha'] as const).map((k) => (
                <div key={k} className="input input-mono tt-ability">
                  <div className="tt-ability-label">{k.toUpperCase()}</div>
                  <div className="tt-ability-value">{(derived.stats as any)[k] ?? '—'}</div>
                </div>
              ))}
            </div>
          </div>

          {derived.inventory.length ? <ListPreview title="Inventory" items={derived.inventory} /> : null}
          {derived.inventoryItems.length ? <InventoryList items={derived.inventoryItems} /> : null}

          {(derived.spells.length || derived.spellSlots.length) ? (
            <div className="card tt-sheet-card">
              <div className="muted" style={{ marginBottom: 6 }}>Spellcasting</div>
              {derived.spellSlots.length ? (
                <div className="row-wrap" style={{ gap: 8, marginBottom: derived.spells.length ? 10 : 0 }}>
                  {derived.spellSlots.map((slot) => (
                    <div key={slot.level} className="input input-mono" style={{ padding: '6px 8px' }}>
                      <strong>L{slot.level}:</strong> {slot.used ?? 0}/{slot.max ?? '—'}
                    </div>
                  ))}
                </div>
              ) : null}
              {derived.spells.length ? (
                <ListPreview title="Spells" items={derived.spells} />
              ) : null}
            </div>
          ) : null}

          {derived.classFeatures.length ? <ListPreview title="Class Features" items={derived.classFeatures} onItemClick={(it) => { const d = findDetailForFeature(it); setDetailTitle(it); setDetailText(d || it); setDetailOpen(true) }} /> : null}
          {derived.racialFeatures.length ? <ListPreview title="Racial Features" items={derived.racialFeatures} onItemClick={(it) => { const d = findDetailForFeature(it); setDetailTitle(it); setDetailText(d || it); setDetailOpen(true) }} /> : null}
          {!derived.classFeatures.length && !derived.racialFeatures.length && derived.features.length ? (
            <ListPreview title="Features" items={derived.features} onItemClick={(it) => { const d = findDetailForFeature(it); setDetailTitle(it); setDetailText(d || it); setDetailOpen(true) }} />
          ) : null}

          {/* Actions */}
          {derived.actions && derived.actions.length ? (
            <div className="card tt-sheet-card">
              <div className="muted" style={{ marginBottom: 6 }}>Actions</div>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {derived.actions.map((a: any, idx: number) => (
                  <li key={`action-${idx}`}>
                    <button className="btn btn-ghost" style={{ padding: 0, textAlign: 'left' }} onClick={() => { setDetailTitle(a.name || 'Action'); setDetailText(a.detail || ''); setDetailOpen(true) }}>{a.name}</button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {/* Bonus actions */}
          {derived.bonusActions && derived.bonusActions.length ? (
            <div className="card tt-sheet-card">
              <div className="muted" style={{ marginBottom: 6 }}>Bonus Actions</div>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {derived.bonusActions.map((a: any, idx: number) => (
                  <li key={`baction-${idx}`}>
                    <button className="btn btn-ghost" style={{ padding: 0, textAlign: 'left' }} onClick={() => { setDetailTitle(a.name || 'Bonus Action'); setDetailText(a.detail || ''); setDetailOpen(true) }}>{a.name}</button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {/* Skills */}
          {derived.skills && derived.skills.length ? (
            <div className="card tt-sheet-card">
              <div className="muted" style={{ marginBottom: 6 }}>Skills</div>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {derived.skills.map((s) => <li key={s}>{s}</li>)}
              </ul>
            </div>
          ) : null}

          {showRaw ? (
            <div className="card tt-sheet-card">
              <div className="muted" style={{ marginBottom: 6 }}>Raw sheet JSON</div>
              <pre className="code-block tt-sheet-raw">
                {JSON.stringify(sheet, null, 2)}
              </pre>
            </div>
          ) : null}

          {/* Simple edit panel to adjust parsed PDF fields (stats, AC, HP, features) */}
          {!editing ? (
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button className="btn btn-quiet" type="button" onClick={beginEdit}>
                Edit character
              </button>
            </div>
          ) : null}

          {editing ? (
            <div className="card card-pad stack" style={{ background: 'rgba(255,255,255,0.02)' }}>
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
                {(['str','dex','con','int','wis','cha'] as const).map((k) => (
                  <div key={k} className="stack" style={{ gap: 6 }}>
                    <label className="muted">{k.toUpperCase()}</label>
                    <input className="input input-mono" value={String(editSheet?.stats?.[k] ?? '')} onChange={(e) => { setEditSheet((s: any)=>({ ...s, stats: { ...(s?.stats||{}), [k]: parseInt(e.target.value || '0',10) }})) }} />
                  </div>
                ))}
                <div className="stack" style={{ gap: 6 }}>
                  <label className="muted">AC</label>
                  <input className="input input-mono" value={String(editSheet?.ac ?? '')} onChange={(e)=>setEditSheet((s:any)=>({ ...s, ac: Number(e.target.value || 0)}))} />
                </div>
                <div className="stack" style={{ gap: 6 }}>
                  <label className="muted">HP max</label>
                  <input className="input input-mono" value={String(editSheet?.hp?.max ?? '')} onChange={(e)=>setEditSheet((s:any)=>({ ...s, hp: { ...(s?.hp||{}), max: Number(e.target.value || 0)}}))} />
                </div>
                <div className="stack" style={{ gap: 6 }}>
                  <label className="muted">HP current</label>
                  <input className="input input-mono" value={String(editSheet?.hp?.current ?? '')} onChange={(e)=>setEditSheet((s:any)=>({ ...s, hp: { ...(s?.hp||{}), current: Number(e.target.value || 0)}}))} />
                </div>
              </div>
              <div style={{ marginTop: 8 }}>
                <label className="muted">Features (one per line)</label>
                <textarea className="input" rows={6} value={Array.isArray(editSheet?.features) ? editSheet.features.join('\n') : String(editSheet?.features || '')} onChange={(e)=>setEditSheet((s:any)=>({ ...s, features: e.target.value.split('\n').map((r:string)=>r.trim()).filter(Boolean)}))} />
              </div>
              <div className="row-wrap" style={{ justifyContent: 'flex-end', gap: 8 }}>
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
                    const res = await apiFetch(`/characters/${character.id}`, { method: 'PUT', body: JSON.stringify(payload) })
                    if(!res.ok){ const err = await res.json().catch(()=>({})); alert(err?.detail || 'Failed to save'); return }
                    // refresh: close modal and let parent reload if needed
                    setEditing(false)
                    setEditSheet(null)
                    if (onSaved) await onSaved()
                    onClose()
                  }catch(e:any){ alert(e?.message||'Network error') }finally{ setSaveBusy(false) }
                }}>Save</button>
              </div>
            </div>
          ) : null}

          <Modal open={detailOpen} title={detailTitle || 'Detail'} onClose={() => setDetailOpen(false)}>
            <div className="stack" style={{ gap: 8 }}>
              <div style={{ whiteSpace: 'pre-wrap', fontSize: 14 }}>{detailText || 'No additional details available.'}</div>
              {/* Show any attached references for this feature/spell */}
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
                            <div style={{ fontSize: 13 }}><strong>{String(r.source_id)}</strong> • Page {String(r.page)}</div>
                            <div className="muted" style={{ fontSize: 13, marginBottom: 6 }}>{r.snippet}</div>
                            <div style={{ display: 'flex', gap: 8 }}>
                              <a className="btn btn-quiet btn-sm" target="_blank" rel="noreferrer" href={`${API_BASE}/references/${encodeURIComponent(String(r.source_id))}/raw#page=${encodeURIComponent(String(r.page))}`}>Open source</a>
                            </div>
                          </li>
                        ))}
                      </ul>
                    )
                  })()}
                </div>
              ) : null}
              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <button className="btn btn-secondary" type="button" onClick={() => setDetailOpen(false)}>Close</button>
              </div>
            </div>
          </Modal>
          

          {!ddbUrl && !Object.keys(derived.raw || {}).length ? (
            <div className="inline-alert" style={{ marginTop: 6 }}>
              This character was created from a link and doesn’t have a parsed sheet yet. If you want full stats/spells,
              import a JSON export.
            </div>
          ) : null}
        </div>
      )}
    </Modal>
  )
}
