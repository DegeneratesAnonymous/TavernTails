/**
 * A staged builder: one question at a time, cards plus room for the player's own words, ending in a narrative of
 * their choices that they can edit. Used for the world and for a character's backstory.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react'
import {
  ALIGNMENTS,
  TRAIT_OPTIONS,
  answerFor,
  emptyAnswer,
  entriesFor,
  linkOf,
  stageDone,
  stageOptions,
  worldContextFromAnswers,
  type Answers,
  type Entry,
  type LinkChoice,
  type Stage,
  type WorldContext,
} from '../../data/lifepath'
import { draftNarrative, type NarrativeResult } from './lifepathApi'
import '../dashboard/wizard.css'
import './LifePath.css'

export type LifePathResult = {
  answers: Answers
  narrative: string
  entries: Entry[]
  link: LinkChoice | null
  world: WorldContext
}

type Props = {
  kind: 'world' | 'character'
  title: string
  stages: Stage[]
  /** The character's name, or the world's name once known. */
  name: string
  /** For a character: the world it is set in. A world builds its own from the answers. */
  world: WorldContext
  initialAnswers?: Answers
  doneLabel: string
  busy?: boolean
  onCancel: () => void
  onDone: (result: LifePathResult) => void | Promise<void>
  /** Called whenever the answers or the narrative change. */
  onChange?: (state: LifePathResult) => void
  /** Shown under the narrative, e.g. where to save it. */
  renderFinish?: (state: LifePathResult) => React.ReactNode
  /** Disables the done button, e.g. while a required choice below the narrative is missing. */
  finishBlocked?: boolean
}

export default function LifePathBuilder({
  kind, title, stages, name, world, initialAnswers, doneLabel, busy, onCancel, onDone, onChange, renderFinish, finishBlocked,
}: Props) {
  const [answers, setAnswers] = useState<Answers>(initialAnswers ?? {})
  const [index, setIndex] = useState(0)
  const [seen, setSeen] = useState(0)
  const [narrative, setNarrative] = useState('')
  const [edited, setEdited] = useState(false)
  const [freeform, setFreeform] = useState('')
  const [drafting, setDrafting] = useState(false)
  const [source, setSource] = useState<NarrativeResult['source'] | null>(null)
  const [draftedFor, setDraftedFor] = useState('')
  const [error, setError] = useState<string | null>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)

  const atNarrative = index >= stages.length
  const stage = stages[index]
  const resolvedWorld = useMemo(
    () => (kind === 'world' ? worldContextFromAnswers(stages, answers) : world),
    [kind, stages, answers, world],
  )
  const entries = useMemo(() => entriesFor(stages, answers), [stages, answers])
  const link = useMemo(() => linkOf(stages, answers, resolvedWorld), [stages, answers, resolvedWorld])
  const signature = JSON.stringify({ entries, link, freeform })

  useEffect(() => { headingRef.current?.focus() }, [index])

  const update = (id: string, change: (a: ReturnType<typeof emptyAnswer>) => ReturnType<typeof emptyAnswer>) =>
    setAnswers((prev) => ({ ...prev, [id]: change(answerFor(prev, id)) }))

  async function draft() {
    const forSignature = signature
    setDrafting(true)
    setError(null)
    const out = await draftNarrative({
      kind, name: name || resolvedWorld.world_name, entries, freeform, link: kind === 'character' ? link : null, context: resolvedWorld,
    })
    setDraftedFor(forSignature) // what this draft was written from, even if it failed, so a failure is not retried in a loop
    setDrafting(false)
    if (!out) {
      setError('Could not draft that just now. You can write it yourself below.')
      return
    }
    setNarrative(out.narrative)
    setSource(out.source)
    setEdited(false)
  }

  // Write the story when it is first reached, and again if the choices changed while an earlier draft was being
  // written (the player went back and changed something). Edited text is never replaced without being asked.
  useEffect(() => {
    if (!atNarrative || drafting) return
    if (draftedFor === '' || (draftedFor !== signature && !edited)) void draft()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [atNarrative, drafting, signature, draftedFor, edited])

  const go = (next: number) => {
    setIndex(next)
    setSeen((s) => Math.max(s, next))
  }

  const state: LifePathResult = { answers, narrative, entries, link, world: resolvedWorld }
  useEffect(() => { onChange?.(state) }, [narrative, signature]) // eslint-disable-line react-hooks/exhaustive-deps
  const stale = atNarrative && !!narrative && draftedFor !== signature

  return (
    <div className="lifepath" role="group" aria-label={title}>
      <nav className="lifepath-rail" aria-label="Steps">
        {[...stages.map((s) => s.title), 'Your story'].map((label, i) => (
          <button
            key={label}
            type="button"
            className={i < index || i < seen ? 'is-done' : ''}
            aria-current={i === index ? 'step' : undefined}
            disabled={i > seen}
            onClick={() => go(i)}
          >
            {label}
          </button>
        ))}
      </nav>

      {!atNarrative && stage && (
        <section>
          <h2 ref={headingRef} tabIndex={-1}>{stage.question}</h2>
          {stage.hint && <p className="lifepath-hint">{stage.hint}</p>}
          <StageBody stage={stage} answers={answers} update={update} />
          <div className="lifepath-actions" style={{ marginTop: 16 }}>
            <button className="btn btn-secondary" type="button" onClick={index === 0 ? onCancel : () => go(index - 1)}>
              {index === 0 ? 'Cancel' : 'Back'}
            </button>
            <button className="btn btn-primary" type="button" disabled={!stageDone(stage, answers)} onClick={() => go(index + 1)}>
              {index === stages.length - 1 ? 'Write it up' : stage.required ? 'Next' : entries.some((e) => e.stage === stage.id) ? 'Next' : 'Skip'}
            </button>
          </div>
          {stage.required && !stageDone(stage, answers) && (
            <p className="lifepath-note" role="status">
              {stage.kind === 'link' ? 'Pick how your story touches the main trouble, or let the story decide.' : stage.kind === 'powers' ? 'Name at least one power to continue.' : stage.kind === 'places' ? 'Name at least one place to continue.' : stage.kind === 'goals' ? 'Write a long goal to continue.' : 'Choose one, or write your own, to continue.'}
            </p>
          )}
        </section>
      )}

      {atNarrative && (
        <section>
          <h2 ref={headingRef} tabIndex={-1}>{kind === 'world' ? 'Your world' : `${name || 'Your character'}’s story`}</h2>
          <p className="lifepath-hint">
            Written from your choices. Change anything — this is yours.
            {source === 'template' && ' (The writer was unavailable, so this is a plain summary.)'}
          </p>
          {drafting && <p role="status">Writing…</p>}
          <label>
            <span className="sr-only">Your story</span>
            <textarea
              className="input lifepath-narrative"
              value={narrative}
              disabled={drafting}
              onChange={(e) => { setNarrative(e.target.value); setEdited(true) }}
              aria-label="Narrative"
            />
          </label>
          {error && <div className="alert alert-error">{error}</div>}
          {stale && (
            <p className="lifepath-note" role="status">
              Your choices changed since this was written. Rewrite to include them{edited ? ' (your edits will be replaced)' : ''}.
            </p>
          )}
          <label style={{ marginTop: 8 }}>
            Anything else you want in it?
            <textarea className="input" value={freeform} onChange={(e) => setFreeform(e.target.value)} placeholder="Optional. Added the next time it is written." />
          </label>
          <div className="lifepath-actions" style={{ marginTop: 8 }}>
            <button
              className="btn btn-secondary" type="button" disabled={drafting}
              onClick={() => { if (!edited || window.confirm('Replace your edits with a new draft?')) void draft() }}
            >
              Write it again
            </button>
          </div>
          {renderFinish?.(state)}
          <div className="lifepath-actions" style={{ marginTop: 16 }}>
            <button className="btn btn-secondary" type="button" onClick={() => go(stages.length - 1)}>Back</button>
            <button
              className="btn btn-primary" type="button"
              disabled={busy || drafting || !narrative.trim() || finishBlocked}
              onClick={() => void onDone(state)}
            >
              {doneLabel}
            </button>
          </div>
        </section>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────
// Stage bodies
// ─────────────────────────────────────────────

type StageBodyProps = {
  stage: Stage
  answers: Answers
  update: (id: string, change: (a: ReturnType<typeof emptyAnswer>) => ReturnType<typeof emptyAnswer>) => void
}

function Field({ stageId, field, label, placeholder, a, update }: {
  stageId: string; field: string; label: string; placeholder?: string
  a: ReturnType<typeof emptyAnswer>; update: StageBodyProps['update']
}) {
  return (
    <label>
      {label}
      <input
        className="input"
        value={a.fields[field] ?? ''}
        placeholder={placeholder}
        maxLength={160}
        onChange={(e) => update(stageId, (x) => ({ ...x, fields: { ...x.fields, [field]: e.target.value } }))}
      />
    </label>
  )
}

function StageBody({ stage, answers, update }: StageBodyProps) {
  const a = answerFor(answers, stage.id)
  const options = stageOptions(stage, answers)
  const field = (f: string, label: string, placeholder?: string) => (
    <Field key={f} stageId={stage.id} field={f} label={label} placeholder={placeholder} a={a} update={update} />
  )

  if (stage.kind === 'choice' || stage.kind === 'link') {
    return (
      <>
        <div className="lifepath-cards" role="radiogroup" aria-label={stage.question}>
          {options.map((o) => (
            <button
              key={o.id}
              type="button"
              role="radio"
              aria-checked={a.picked[0] === o.id}
              className={`wizard-option-card${a.picked[0] === o.id ? ' is-selected' : ''}`}
              onClick={() => update(stage.id, (x) => ({ ...x, picked: x.picked[0] === o.id ? [] : [o.id], typed: x.picked[0] === o.id ? x.typed : '' }))}
            >
              <span className="wizard-option-name">{o.label}</span>
            </button>
          ))}
        </div>
        <label style={{ marginTop: 10 }}>
          {stage.typedLabel ?? 'Something else'}
          <textarea
            className="input"
            value={a.typed}
            maxLength={400}
            onChange={(e) => update(stage.id, (x) => ({ ...x, typed: e.target.value, picked: e.target.value.trim() ? [] : x.picked }))}
            placeholder="In your own words"
          />
        </label>
      </>
    )
  }
  if (stage.kind === 'text') {
    return (
      <label>
        <span className="sr-only">{stage.question}</span>
        <textarea
          className="input"
          value={a.typed}
          maxLength={400}
          placeholder={stage.typedPlaceholder}
          onChange={(e) => update(stage.id, (x) => ({ ...x, typed: e.target.value }))}
        />
      </label>
    )
  }
  if (stage.kind === 'powers') {
    return (
      <div style={{ display: 'grid', gap: 10 }}>
        {[0, 1, 2].map((i) => (
          <div className="lifepath-row" key={i}>
            {field(`name${i}`, i === 0 ? 'A power (required)' : 'Another power', 'The Salt Court')}
            {field(`wants${i}`, 'What it wants', 'to control the grain')}
          </div>
        ))}
      </div>
    )
  }
  if (stage.kind === 'places') {
    return (
      <div className="lifepath-row">
        {[0, 1, 2, 3].map((i) => field(`p${i}`, i === 0 ? 'A place (required)' : 'Another place', 'The Ashen Market'))}
      </div>
    )
  }
  if (stage.kind === 'ties') {
    return (
      <div style={{ display: 'grid', gap: 10 }}>
        {field('ally', 'An ally', 'Tam, a ferryman who owes me')}
        {field('rival', 'A rival or enemy', 'A magistrate who wants me quiet')}
        {field('patron', 'A patron', 'The guild that pays my debts')}
      </div>
    )
  }
  if (stage.kind === 'traits') {
    const toggle = (key: 'ideals' | 'flaws' | 'bonds', id: string) =>
      update(stage.id, (x) => {
        const current = (x.fields[`${key}_picked`] ?? '').split(',').filter(Boolean)
        const next = current.includes(id) ? current.filter((c) => c !== id) : [...current, id].slice(-2)
        return { ...x, fields: { ...x.fields, [`${key}_picked`]: next.join(',') } }
      })
    const group = (key: 'ideals' | 'flaws' | 'bonds', label: string) => (
      <div key={key}>
        <div className="lifepath-note">{label} (up to two)</div>
        <div className="lifepath-chips">
          {TRAIT_OPTIONS[key].map((o) => {
            const on = (a.fields[`${key}_picked`] ?? '').split(',').includes(o.id)
            return (
              <button key={o.id} type="button" aria-pressed={on} className={on ? 'is-selected' : ''} onClick={() => toggle(key, o.id)}>
                {o.label}
              </button>
            )
          })}
        </div>
        {field(`${key}_t`, `Your own ${label.toLowerCase()}`)}
      </div>
    )
    return (
      <div style={{ display: 'grid', gap: 12 }}>
        <label>
          Alignment
          <select className="input" value={a.fields.alignment ?? ''} onChange={(e) => update(stage.id, (x) => ({ ...x, fields: { ...x.fields, alignment: e.target.value } }))}>
            <option value="">Not sure yet</option>
            {ALIGNMENTS.map((al) => <option key={al} value={al}>{al}</option>)}
          </select>
        </label>
        {group('ideals', 'Ideals')}
        {group('bonds', 'Bonds')}
        {group('flaws', 'Flaws')}
        {field('traits_t', 'How you act, day to day', 'Dry humour, never sits with their back to a door')}
      </div>
    )
  }
  // goals
  return (
    <div style={{ display: 'grid', gap: 12 }}>
      {([
        ['long', 'Long goal (required)', 'What this story is about. It should bear on the main trouble.'],
        ['mid', 'Mid goal', 'Something that will take a while.'],
        ['short', 'Short goal', 'A first step you could take in a few sessions.'],
      ] as const).map(([term, label, hint]) => (
        <div className="lifepath-goal" key={term}>
          <strong>{label}</strong>
          <span className="lifepath-note">{hint}</span>
          {field(`${term}_text`, 'My character wants to…', 'find who burned the granary')}
          <div className="lifepath-goal-row">
            {field(`${term}_because`, '…because', 'it was the only thing keeping my street fed')}
            {field(`${term}_but`, '…but', 'the main witness has left town')}
          </div>
        </div>
      ))}
    </div>
  )
}
