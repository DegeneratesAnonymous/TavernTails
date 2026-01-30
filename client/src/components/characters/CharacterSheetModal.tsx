import React, { useMemo, useState } from 'react'

import Modal from '../ui/Modal'

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

export default function CharacterSheetModal({ open, character, loading = false, onClose }: Props) {
  const [showRaw, setShowRaw] = useState(false)

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

  const derived = useMemo(() => {
    const raw = (sheet?.raw && typeof sheet.raw === 'object') ? sheet.raw : {}
    const stats = (sheet?.stats && typeof sheet.stats === 'object') ? sheet.stats : {}

    const hpCurrent = asNumber(sheet?.hp?.current ?? sheet?.hp_current, 0)
    const hpMax = asNumber(sheet?.hp?.max ?? sheet?.hp_max, 0)
    const ac = asNumber(sheet?.ac, 0)

    return {
      hpCurrent: hpCurrent || null,
      hpMax: hpMax || null,
      ac: ac || null,
      stats: {
        str: asNumber(stats?.str, 0) || null,
        dex: asNumber(stats?.dex, 0) || null,
        con: asNumber(stats?.con, 0) || null,
        int: asNumber(stats?.int, 0) || null,
        wis: asNumber(stats?.wis, 0) || null,
        cha: asNumber(stats?.cha, 0) || null,
      },
      inventory: joinList(sheet?.inventory),
      spells: joinList(sheet?.spells),
      features: joinList(sheet?.features),
      raw,
    }
  }, [sheet])

  const title = character ? `${character.name} (L${character.level}${character.class_name ? ` ${character.class_name}` : ''})` : 'Character Sheet'

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

          {derived.inventory.length ? (
            <div className="card tt-sheet-card">
              <div className="muted" style={{ marginBottom: 6 }}>Inventory</div>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {derived.inventory.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </div>
          ) : null}

          {derived.spells.length ? (
            <div className="card tt-sheet-card">
              <div className="muted" style={{ marginBottom: 6 }}>Spells</div>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {derived.spells.map((spell) => <li key={spell}>{spell}</li>)}
              </ul>
            </div>
          ) : null}

          {derived.features.length ? (
            <div className="card tt-sheet-card">
              <div className="muted" style={{ marginBottom: 6 }}>Features</div>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {derived.features.map((feat) => <li key={feat}>{feat}</li>)}
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
