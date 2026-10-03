import React, { useRef, useState, useMemo, useEffect } from 'react'
import { CharacterSummary } from '../CharacterPanel'

const DICE = [4, 6, 8, 10, 12, 20]

function addDie(current: string, sides: number): string {
  const trimmed = current.trim()
  const m = trimmed.match(new RegExp(`^(\\d+)d${sides}$`, 'i'))
  return m ? `${parseInt(m[1], 10) + 1}d${sides}` : `1d${sides}`
}

type Suggestion = {
  label: string
  tag: string
  type: 'spell' | 'skill' | 'ability' | 'feature' | 'item'
}

const ABILITY_LABELS: Suggestion[] = [
  { label: 'STR', tag: 'str', type: 'ability' },
  { label: 'DEX', tag: 'dex', type: 'ability' },
  { label: 'CON', tag: 'con', type: 'ability' },
  { label: 'INT', tag: 'int', type: 'ability' },
  { label: 'WIS', tag: 'wis', type: 'ability' },
  { label: 'CHA', tag: 'cha', type: 'ability' },
]

type Props = {
  sessionId: string | null | undefined
  value: string
  onChange: (v: string) => void
  onSend: () => void
  rolling?: boolean
  character?: CharacterSummary | null
}

export default function Composer({ sessionId, value, onChange, onSend, rolling, character }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [acIndex, setAcIndex] = useState(0)

  const allSuggestions = useMemo((): Suggestion[] => {
    const items: Suggestion[] = [...ABILITY_LABELS]
    character?.skills?.forEach(s => {
      items.push({ label: s.name, tag: s.name.replace(/\s+/g, '_'), type: 'skill' })
    })
    const spellSeen = new Set<string>()
    character?.spellbook?.forEach((e: any) => {
      if (e?.name && !spellSeen.has(e.name)) {
        spellSeen.add(e.name)
        items.push({ label: e.name, tag: e.name.replace(/\s+/g, '_'), type: 'spell' })
      }
    })
    character?.classFeatures?.forEach(f => {
      items.push({ label: f.name, tag: f.name.replace(/\s+/g, '_'), type: 'feature' })
    })
    character?.inventory?.forEach(item => {
      items.push({ label: item, tag: item.replace(/\s+/g, '_'), type: 'item' })
    })
    return items
  }, [character])

  // Detect trailing @query in value
  const atQuery = useMemo(() => {
    const m = value.match(/@([\w']*)$/)
    return m ? m[1] : null
  }, [value])

  const filtered = useMemo(() => {
    if (atQuery === null) return []
    const q = atQuery.toLowerCase()
    return allSuggestions.filter(s =>
      s.label.toLowerCase().startsWith(q) || s.tag.toLowerCase().startsWith(q)
    ).slice(0, 8)
  }, [atQuery, allSuggestions])

  useEffect(() => { setAcIndex(0) }, [filtered])

  const selectSuggestion = (item: Suggestion) => {
    const lastAt = value.lastIndexOf('@')
    onChange(value.slice(0, lastAt) + '@' + item.tag + ' ')
    inputRef.current?.focus()
  }

  const handleDie = (sides: number) => {
    onChange(addDie(value, sides))
    inputRef.current?.focus()
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (filtered.length === 0) return
    if (e.key === 'ArrowDown') { e.preventDefault(); setAcIndex(i => Math.min(i + 1, filtered.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setAcIndex(i => Math.max(i - 1, 0)) }
    else if (e.key === 'Enter' && filtered.length > 0) {
      e.preventDefault()
      selectSuggestion(filtered[acIndex])
    } else if (e.key === 'Escape') {
      onChange(value.replace(/@[\w']*$/, ''))
    }
  }

  const tagTypeClass: Record<Suggestion['type'], string> = {
    ability: 'ac-type--ability',
    skill: 'ac-type--skill',
    spell: 'ac-type--spell',
    feature: 'ac-type--feature',
    item: 'ac-type--item',
  }

  return (
    <div className="chat-composer-wrap">
      {filtered.length > 0 ? (
        <div className="chat-ac-dropdown">
          {filtered.map((s, i) => (
            <button
              key={s.tag}
              type="button"
              className={`chat-ac-item ${i === acIndex ? 'chat-ac-item--active' : ''}`}
              onMouseDown={e => { e.preventDefault(); selectSuggestion(s) }}
            >
              <span className={`chat-ac-type ${tagTypeClass[s.type]}`}>{s.type[0].toUpperCase()}</span>
              <span className="chat-ac-label">{s.label}</span>
            </button>
          ))}
        </div>
      ) : null}

      <form className="chat-composer-row" onSubmit={e => { e.preventDefault(); if (!rolling) onSend() }}>
        <div className="chat-composer-dice">
          {DICE.map(s => (
            <button
              key={s}
              type="button"
              className="chat-die-btn"
              title={`d${s}`}
              disabled={!sessionId || rolling}
              onClick={() => handleDie(s)}
            >
              d{s}
            </button>
          ))}
        </div>
        <input
          ref={inputRef}
          className="chat-composer-input"
          value={value}
          onChange={e => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={sessionId ? 'Message… type @ to reference character' : 'Select a session'}
          disabled={!sessionId || rolling}
          autoComplete="off"
        />
        <button
          className={`chat-composer-send ${rolling ? 'chat-composer-send--rolling' : ''}`}
          type="submit"
          disabled={!sessionId || !value.trim() || rolling}
          aria-label={rolling ? 'Rolling…' : 'Send'}
        >
          {rolling ? '⚄' : '↑'}
        </button>
      </form>
    </div>
  )
}
