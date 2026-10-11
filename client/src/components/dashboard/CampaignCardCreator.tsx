/**
 * One-screen campaign creation.
 *
 * The player describes the game they want in their own words (a genre
 * button, a seed or their setting notes can start the text for them). One
 * model call reads it back as a Campaign Card: what they said, what was
 * guessed, and what is still open. They fix anything wrong, answer at most two
 * questions the first scene needs, and create. The world skeleton is then
 * built in the background while they pick or build a character.
 */

import React, { useEffect, useState } from 'react'
import { apiFetch } from '../../api'
import {
  FREEDOM_OPTIONS,
  GENRE_OPTIONS,
  MAIN_FIELDS,
  buildCreatePayload,
  editField,
  groupFields,
  openFieldsWithoutFollowUps,
  type CampaignCard,
  type WorldVisibility,
} from './campaignCard'

type SeedOption = { id: string; title: string; tagline: string; setting_summary: string; emoji: string }

const GENRE_STARTERS: { id: string; label: string; emoji: string; text: string }[] = [
  { id: 'fantasy', label: 'Fantasy', emoji: '🏰', text: 'A fantasy campaign of magic, monsters, and old prophecies.' },
  { id: 'horror', label: 'Horror', emoji: '🕯️', text: 'A horror campaign full of dread and things that should not be.' },
  { id: 'sci-fi', label: 'Sci-Fi', emoji: '🚀', text: 'A science-fiction campaign of starships, strange worlds, and hard choices.' },
  { id: 'mystery', label: 'Mystery', emoji: '🔍', text: 'A mystery campaign: clues, lies, and someone who knows more than they say.' },
  { id: 'political', label: 'Political', emoji: '👑', text: 'A political campaign of factions, ambition, and consequences that last.' },
  { id: 'post-apocalyptic', label: 'Survival', emoji: '🌋', text: 'A survival campaign where resources run out and trust is a luxury.' },
]

/** The server accepts this many content limits on a card (ConfirmedCard.content_limits). */
const MAX_LIMITS = 8

const STATUS_LABELS = {
  said: { title: 'You said', help: 'Taken from your words.' },
  guessed: { title: 'I guessed', help: 'Change anything that is not right.' },
  open: { title: 'Still open', help: 'Left for the story to decide unless you fill it in.' },
} as const

type Props = {
  seat: React.ReactNode
  owner: { owner_role: 'player' | 'dm'; owner_character_id: number | null }
  validateSeat: () => string | null
  fallbackName: string
  onCreated: (campaignId: string, sessionId: string | null) => void
  onClassic: () => void
}

export default function CampaignCardCreator({ seat, owner, validateSeat, fallbackName, onCreated, onClassic }: Props) {
  const [text, setText] = useState('')
  // The sentence a starter put in the box, so another starter can replace it (but never the player's own words).
  const [autoText, setAutoText] = useState<string | null>(null)
  const [starter, setStarter] = useState<Record<string, string>>({})
  const [lore, setLore] = useState('')
  const [showLore, setShowLore] = useState(false)
  const [showSeeds, setShowSeeds] = useState(false)
  const [seeds, setSeeds] = useState<SeedOption[]>([])
  const [card, setCard] = useState<CampaignCard | null>(null)
  const [arrival, setArrival] = useState<CampaignCard | null>(null)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [newLimit, setNewLimit] = useState('')
  const [visibility, setVisibility] = useState<WorldVisibility>('surprise')
  const [generateWorld, setGenerateWorld] = useState(true)
  const [busy, setBusy] = useState<'reading' | 'creating' | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!showSeeds || seeds.length) return
    let live = true
    apiFetch('/campaigns/seeds')
      .then((r) => r.json())
      .then((d) => { if (live) setSeeds(d.seeds ?? []) })
      .catch(() => {})
    return () => { live = false }
  }, [showSeeds, seeds.length])

  function fillFromStarter(next: string | null) {
    const untouched = !text.trim() || text === autoText
    if (!untouched) return
    setText(next ?? '')
    setAutoText(next)
  }

  function pickGenre(id: string, starterText: string) {
    const same = starter.genre === id && !starter.seed_id
    setStarter(same ? {} : { genre: id })
    fillFromStarter(same ? null : starterText)
  }

  function pickSeed(seed: SeedOption) {
    setStarter({ seed_id: seed.id })
    fillFromStarter(seed.setting_summary)
    setShowSeeds(false)
  }

  async function onLoreFile(file: File | undefined) {
    if (!file) return
    try {
      const content = await file.text()
      setLore((prev) => (prev ? `${prev}\n\n${content}` : content).slice(0, 60000))
    } catch {
      setError('That file could not be read. Paste the text instead.')
    }
  }

  async function readBack() {
    setBusy('reading')
    setError(null)
    try {
      const res = await apiFetch('/campaigns/card', {
        method: 'POST',
        body: JSON.stringify({ text, starter, lore: lore.trim() || null }),
      })
      if (!res.ok) throw new Error('Could not read that back. Please try again.')
      const body = await res.json()
      setCard(body.card)
      setArrival(body.card)
      setAnswers({})
    } catch (e: any) {
      setError(e?.message || 'Could not read that back. Please try again.')
    } finally {
      setBusy(null)
    }
  }

  async function create() {
    if (!card) return
    const seatError = validateSeat()
    if (seatError) {
      setError(seatError)
      document.getElementById('campaign-seat')?.scrollIntoView({ block: 'center', behavior: 'smooth' })
      return
    }
    setBusy('creating')
    setError(null)
    try {
      const res = await apiFetch('/campaigns', {
        method: 'POST',
        body: JSON.stringify(buildCreatePayload({ card, answers, fallbackName, visibility, generateWorld, lore, owner })),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => null)
        throw new Error(err?.detail || 'Failed to create campaign')
      }
      const body = await res.json()
      const campaign = body?.campaign ?? body
      if (!campaign?.id) throw new Error('Campaign created but ID not returned')
      const sessions = Array.isArray(campaign.sessions) ? campaign.sessions : []
      onCreated(String(campaign.id), sessions[0]?.id ? String(sessions[0].id) : null)
    } catch (e: any) {
      setError(e?.message || 'Something went wrong. Please try again.')
    } finally {
      setBusy(null)
    }
  }

  if (!card || !arrival) {
    return (
      <div className="wizard-body card-creator">
        <div>
          <div className="wizard-step-heading">What game do you want to play?</div>
          <div className="wizard-step-sub">
            Describe it however you like: the place, the trouble, the feel, the rules you use. I'll read it back so you can check it.
          </div>
        </div>
        {/* Frozen while reading: the card that comes back is built from what was sent. */}
        <fieldset className="card-creator-inputs" disabled={busy === 'reading'}>
          <textarea
            className="input card-creator-text"
            aria-label="Describe your campaign"
            value={text}
            onChange={(e) => { setText(e.target.value); setAutoText(null) }}
            rows={6}
            maxLength={8000}
            placeholder="A grim harbor town where the lighthouse keeper vanished. Political, not much combat. 5e, level 3."
          />
          <div className="card-creator-starters">
            <span className="wizard-control-label">Start from</span>
            <div className="row-wrap" style={{ gap: 6 }}>
              {GENRE_STARTERS.map((g) => (
                <button
                  key={g.id}
                  type="button"
                  className={`wizard-segment card-creator-chip${starter.genre === g.id && !starter.seed_id ? ' is-selected' : ''}`}
                  aria-pressed={starter.genre === g.id && !starter.seed_id}
                  onClick={() => pickGenre(g.id, g.text)}
                >
                  {g.emoji} {g.label}
                </button>
              ))}
              <button
                type="button"
                className={`wizard-segment card-creator-chip${starter.seed_id ? ' is-selected' : ''}`}
                aria-expanded={showSeeds}
                onClick={() => setShowSeeds((v) => !v)}
              >
                📜 A seed
              </button>
              <button
                type="button"
                className={`wizard-segment card-creator-chip${showLore || lore ? ' is-selected' : ''}`}
                aria-expanded={showLore}
                onClick={() => setShowLore((v) => !v)}
              >
                📎 My setting notes
              </button>
            </div>
          </div>
          {showSeeds && (
            <div className="card-creator-seeds">
              {seeds.length === 0 && <div className="muted">Loading seeds…</div>}
              {seeds.map((seed) => (
                <button
                  key={seed.id}
                  type="button"
                  className={`wizard-path-card${starter.seed_id === seed.id ? ' is-selected' : ''}`}
                  onClick={() => pickSeed(seed)}
                >
                  <strong className="wizard-path-label">{seed.emoji} {seed.title}</strong>
                  <span className="wizard-path-desc">{seed.tagline}</span>
                </button>
              ))}
            </div>
          )}
          {showLore && (
            <div className="wizard-control-group">
              <label className="wizard-control-label" htmlFor="card-lore">Setting notes</label>
              <textarea
                id="card-lore"
                className="input"
                value={lore}
                onChange={(e) => setLore(e.target.value)}
                rows={6}
                maxLength={60000}
                placeholder="Paste lore, a setting bible, or homebrew notes. Names and facts here are kept as canon."
              />
              <input
                type="file"
                accept=".txt,.md,text/plain,text/markdown"
                aria-label="Upload setting notes"
                onChange={(e) => onLoreFile(e.target.files?.[0])}
              />
            </div>
          )}
        </fieldset>
        {error && <div className="inline-alert inline-alert-error wizard-error" role="alert">{error}</div>}
        <div className="wizard-nav">
          <button className="btn btn-quiet" type="button" onClick={onClassic}>Use the classic setup</button>
          <button className="btn" type="button" disabled={busy !== null || !(text.trim() || lore.trim())} onClick={readBack}>
            {busy === 'reading' ? 'Reading it back… (about 10 seconds)' : 'Read it back →'}
          </button>
        </div>
      </div>
    )
  }

  const groups = groupFields(arrival, MAIN_FIELDS.map((f) => f.key))
  const openKeys = openFieldsWithoutFollowUps(arrival, groups.open)
  const fieldLabel = (key: string) => MAIN_FIELDS.find((f) => f.key === key)?.label ?? key
  const freedom = String(card.fields.ai_freedom?.value || 'medium')
  const limitsFull = card.content_limits.length >= MAX_LIMITS

  const renderField = (key: string) => {
    const field = card.fields[key] ?? { value: '', status: 'open' }
    const meta = MAIN_FIELDS.find((f) => f.key === key)
    const edited = field.status === 'said' && arrival.fields[key]?.status !== 'said'
    const id = `card-field-${key}`
    const set = (value: string | number) => setCard(editField(card, key, value))
    let input: React.ReactNode
    if (key === 'genre') {
      input = (
        <select id={id} className="input" value={String(field.value)} onChange={(e) => set(e.target.value)}>
          {GENRE_OPTIONS.map((g) => <option key={g} value={g}>{g}</option>)}
        </select>
      )
    } else if (key === 'starting_level') {
      input = (
        <input
          id={id}
          className="input"
          type="number"
          min={1}
          max={20}
          value={field.value === '' ? '' : Number(field.value)}
          onChange={(e) => set(e.target.value === '' ? '' : Math.max(1, Math.min(20, Number(e.target.value))))}
        />
      )
    } else if (meta?.multiline) {
      input = <textarea id={id} className="input" rows={2} value={String(field.value)} onChange={(e) => set(e.target.value)} />
    } else {
      input = (
        <input
          id={id}
          className="input"
          value={String(field.value)}
          placeholder={key === 'name' ? fallbackName : ''}
          onChange={(e) => set(e.target.value)}
        />
      )
    }
    return (
      <div key={key} className="card-field">
        <label className="wizard-control-label" htmlFor={id}>
          {fieldLabel(key)}
          {edited && <span className="card-field-edited">edited</span>}
        </label>
        {input}
      </div>
    )
  }

  return (
    <div className="wizard-body card-creator">
      <div>
        <div className="wizard-step-heading">Here's what I heard</div>
        <div className="wizard-step-sub">Fix anything that's off. What you leave here becomes the campaign's starting facts.</div>
      </div>
      {card.diagnostics.source === 'fallback' && (
        <div className="inline-alert" role="status">
          The storyteller model didn't answer, so this card only holds what you wrote. You can still create the campaign.
        </div>
      )}

      {(['said', 'guessed'] as const).map((status) => (
        groups[status].length > 0 && (
          <section key={status} className={`card-group card-group--${status}`} aria-label={STATUS_LABELS[status].title}>
            <div className="card-group-head">
              <span className="wizard-section-kicker">{STATUS_LABELS[status].title}</span>
              <span className="wizard-control-help">{STATUS_LABELS[status].help}</span>
            </div>
            <div className="card-group-fields">{groups[status].map(renderField)}</div>
            {status === 'said' && (card.people.length > 0 || card.factions.length > 0) && (
              <div className="row-wrap" style={{ gap: 6 }}>
                {/* The words are the player's, but whether each is a person or a group was the model's call. */}
                {card.people.map((p) => (
                  <span key={`p-${p.name}`} className="badge card-chip">
                    👤 {p.name}{p.role ? `, ${p.role}` : ''}
                    <button type="button" className="card-chip-remove" aria-label={`Remove person: ${p.name}`}
                      onClick={() => setCard({ ...card, people: card.people.filter((x) => x.name !== p.name) })}>×</button>
                  </span>
                ))}
                {card.factions.map((f) => (
                  <span key={`f-${f.name}`} className="badge card-chip">
                    ⚑ {f.name}
                    <button type="button" className="card-chip-remove" aria-label={`Remove faction: ${f.name}`}
                      onClick={() => setCard({ ...card, factions: card.factions.filter((x) => x.name !== f.name) })}>×</button>
                  </span>
                ))}
              </div>
            )}
          </section>
        )
      ))}

      <section className="card-group card-group--extras" aria-label="Limits and themes">
        {/* Everything Create saves is shown here, so nothing is accepted unseen; remove what is wrong. */}
          <div className="card-field">
            <span className="wizard-control-label">Keep out of the story <span className="card-chip-source">you said</span></span>
            <div className="row-wrap" style={{ gap: 6 }}>
              {card.content_limits.map((limit) => (
                <span key={`l-${limit}`} className="badge card-chip">
                  {limit}
                  <button type="button" className="card-chip-remove" aria-label={`Remove limit: ${limit}`}
                    onClick={() => setCard({ ...card, content_limits: card.content_limits.filter((x) => x !== limit) })}>×</button>
                </span>
              ))}
            </div>
            <form
              className="row-wrap card-add-limit"
              onSubmit={(e) => {
                e.preventDefault()
                const value = newLimit.trim()
                if (value && !limitsFull && !card.content_limits.includes(value)) {
                  setCard({ ...card, content_limits: [...card.content_limits, value] })
                }
                setNewLimit('')
              }}
            >
              <input
                className="input"
                aria-label="Add something to keep out of the story"
                placeholder={limitsFull ? `Up to ${MAX_LIMITS} limits` : 'Add a limit, e.g. graphic gore'}
                disabled={limitsFull}
                value={newLimit}
                maxLength={120}
                onChange={(e) => setNewLimit(e.target.value)}
              />
              <button className="btn btn-secondary btn-sm" type="submit" disabled={!newLimit.trim() || limitsFull}>Add</button>
            </form>
          </div>
        {card.themes.length > 0 && (
          <div className="card-field">
            <span className="wizard-control-label">Themes <span className="card-chip-source">I guessed</span></span>
            <div className="row-wrap" style={{ gap: 6 }}>
              {card.themes.map((theme) => (
                <span key={`t-${theme}`} className="badge card-chip">
                  {theme}
                  <button type="button" className="card-chip-remove" aria-label={`Remove theme: ${theme}`}
                    onClick={() => setCard({ ...card, themes: card.themes.filter((x) => x !== theme) })}>×</button>
                </span>
              ))}
            </div>
          </div>
        )}
      </section>

      {(card.follow_ups.length > 0 || openKeys.length > 0 || card.open_questions.length > 0) && (
      <section className="card-group card-group--open" aria-label={STATUS_LABELS.open.title}>
        <div className="card-group-head">
          <span className="wizard-section-kicker">{STATUS_LABELS.open.title}</span>
          <span className="wizard-control-help">{STATUS_LABELS.open.help}</span>
        </div>
        {card.follow_ups.map((q) => (
          <div key={q.id} className="card-field">
            <label className="wizard-control-label" htmlFor={`follow-up-${q.id}`}>{q.question}</label>
            <input
              id={`follow-up-${q.id}`}
              className="input"
              value={answers[q.id] ?? ''}
              placeholder={q.placeholder}
              onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: e.target.value }))}
            />
            {!answers[q.id]?.trim() && <span className="wizard-control-help">Leave blank and the story will decide.</span>}
          </div>
        ))}
        {openKeys.length > 0 && <div className="card-group-fields">{openKeys.map(renderField)}</div>}
        {card.open_questions.length > 0 && (
          <ul className="card-open-questions" aria-label="Open questions the world underneath will answer">
            {card.open_questions.map((q) => (
              <li key={q}>
                {q}
                <button type="button" className="card-chip-remove" aria-label={`Remove question: ${q}`}
                  onClick={() => setCard({ ...card, open_questions: card.open_questions.filter((x) => x !== q) })}>×</button>
              </li>
            ))}
          </ul>
        )}
      </section>
      )}

      {freedom === 'low' ? (
        <section className="card-group card-group--world" aria-label="The world">
          <div className="card-group-head">
            <span className="wizard-section-kicker">The world underneath</span>
          </div>
          <p className="wizard-control-help" style={{ margin: 0 }}>
            You chose &ldquo;Stick to what I wrote&rdquo;, so nothing is invented ahead of play: no hidden truth, factions or
            people beyond yours. Change that under Advanced if you want the world built for you.
          </p>
        </section>
      ) : (
        <section className="card-group card-group--world" aria-label="The world">
          <div className="card-group-head">
            <span className="wizard-section-kicker">The world underneath</span>
          </div>
          <p className="wizard-control-help" style={{ margin: 0 }}>
            While you pick a character, the storyteller quietly decides what's really going on: the hidden truth, the factions,
            the key people and their secrets, and what gets worse if nobody acts. Your facts above always win.
          </p>
          <div className="wizard-segmented card-segmented-2" role="radiogroup" aria-label="Who sees the world">
            <button
              type="button"
              role="radio"
              aria-checked={visibility === 'surprise'}
              className={`wizard-segment${visibility === 'surprise' ? ' is-selected' : ''}`}
              onClick={() => setVisibility('surprise')}
            >
              Keep it a surprise
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={visibility === 'show'}
              className={`wizard-segment${visibility === 'show' ? ' is-selected' : ''}`}
              onClick={() => setVisibility('show')}
            >
              Show me the world
            </button>
          </div>
        </section>
      )}

      <details className="card-advanced">
        <summary>Advanced</summary>
        <div className="wizard-control-group">
          <span className="wizard-control-label">How much may the storyteller invent?</span>
          <div className="wizard-segmented" role="radiogroup" aria-label="How much may the storyteller invent">
            {FREEDOM_OPTIONS.map((opt) => (
              <button
                key={opt.id}
                type="button"
                role="radio"
                aria-checked={freedom === opt.id}
                className={`wizard-segment${freedom === opt.id ? ' is-selected' : ''}`}
                onClick={() => setCard(editField(card, 'ai_freedom', opt.id))}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
        <div className="wizard-control-grid">
          <div className="wizard-control-group">
            <label className="wizard-control-label" htmlFor="card-pacing">Pacing</label>
            <select id="card-pacing" className="input" value={String(card.fields.pacing?.value || 'moderate')} onChange={(e) => setCard(editField(card, 'pacing', e.target.value))}>
              <option value="slow">Slow burn</option>
              <option value="moderate">Moderate</option>
              <option value="fast">Fast</option>
            </select>
          </div>
          <div className="wizard-control-group">
            <label className="wizard-control-label" htmlFor="card-rating">Content</label>
            <select id="card-rating" className="input" value={String(card.fields.content_rating?.value || 'pg-13')} onChange={(e) => setCard(editField(card, 'content_rating', e.target.value))}>
              <option value="family">Family</option>
              <option value="pg-13">PG-13</option>
              <option value="mature">Mature</option>
            </select>
          </div>
        </div>
        <label className="row-wrap" style={{ gap: 8, alignItems: 'center' }}>
          <input type="checkbox" checked={generateWorld} onChange={(e) => setGenerateWorld(e.target.checked)} />
          <span>Build the world underneath before play (uses about a minute of storyteller time)</span>
        </label>
      </details>

      {seat}

      {error && <div className="inline-alert inline-alert-error wizard-error" role="alert">{error}</div>}
      <div className="wizard-nav">
        <button className="btn btn-secondary" type="button" disabled={busy !== null} onClick={() => { setCard(null); setArrival(null) }}>
          ← Change my description
        </button>
        <button className="btn" type="button" disabled={busy !== null} onClick={create}>
          {busy === 'creating' ? 'Creating…' : 'Create Campaign →'}
        </button>
      </div>
    </div>
  )
}
