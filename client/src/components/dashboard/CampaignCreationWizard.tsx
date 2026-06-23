/**
 * CampaignCreationWizard.tsx
 *
 * Narrative questionnaire-style campaign creation.
 * Instead of asking "what tone do you want?", the wizard presents faux
 * adventure-scenario choices (e.g. "Your party opens a door to find: A, B, C")
 * that reveal the player's preferred GM style.
 *
 * Steps:
 *   1. Narrative quiz  (5 scenario questions)
 *   2. Campaign name   (single text input + optional AI suggestion preview)
 *   3. Ruleset         (visual cards)
 *   4. Level           (slider)
 *   5. Review & create (shows inferred tone / genre mood, confirm)
 */

import React, { useState, useCallback } from 'react'
import { apiFetch } from '../../api'
import PageHeader from '../ui/PageHeader'
import {
  CAMPAIGN_QUIZ,
  deriveCampaignSettings,
  type SystemId,
} from '../../data/wizard-data'
import './wizard.css'

// ─────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────

type Step = 'quiz' | 'name' | 'ruleset' | 'level' | 'review'

type CampaignDraft = {
  quizAnswers: Record<string, string>
  name: string
  ruleset: string
  worldName: string
  startingLevel: number
}

const EMPTY_DRAFT: CampaignDraft = {
  quizAnswers: {},
  name: '',
  ruleset: '',
  worldName: '',
  startingLevel: 1,
}

const STEPS: Step[] = ['quiz', 'name', 'ruleset', 'level', 'review']

// ─────────────────────────────────────────────
// Campaign name pool
// ─────────────────────────────────────────────

const RANDOM_CAMPAIGN_NAMES = [
  'The Shattered Crown',
  'Ashes of the Fallen Throne',
  'The Sunken Citadel',
  'Echoes of the Elder War',
  'Blood and Starlight',
  'The Tomb of Forgotten Kings',
  'Shadows Over Veldrath',
  'The Iron Covenant',
  'A Song of Wolves and Winter',
  'The Gilded Serpent',
  'Beyond the Pale Gate',
  'The Last Lantern',
  'Children of the Cursed Moon',
  'Heirs of the Broken Empire',
  'The Verdant Conspiracy',
  'Storm and Ember',
  'Relics of the Void',
  'The Wandering Dark',
  'Salt, Steel, and Sorcery',
  'The Amber Throne',
  'Where Ravens Gather',
  'The Silence Before the War',
  'Pact of the Hollow Gods',
  'The Obsidian League',
  'Fires of the Forgotten Age',
]

const STEP_LABELS: Record<Step, string> = {
  quiz: 'Scenario',
  name: 'Name',
  ruleset: 'System',
  level: 'Level',
  review: 'Review',
}

// ─────────────────────────────────────────────
// Ruleset options
// ─────────────────────────────────────────────

type RulesetOption = {
  id: string
  label: string
  emoji: string
  genre: string
  systemId?: SystemId
}

const RULESET_OPTIONS: RulesetOption[] = [
  { id: 'srd-5.2', label: 'D&D 5e', emoji: '⚔️', genre: 'Heroic Fantasy', systemId: 'dnd5e' },
  { id: 'pathfinder-2e', label: 'Pathfinder 2e', emoji: '🗺️', genre: 'Tactical Fantasy', systemId: 'pf2e' },
  { id: 'pathfinder-1e', label: 'Pathfinder 1e', emoji: '🐉', genre: 'Classic Fantasy', systemId: 'pf1e' },
  { id: 'starfinder', label: 'Starfinder', emoji: '🚀', genre: 'Science Fantasy', systemId: 'starfinder' },
  { id: 'coc', label: 'Call of Cthulhu', emoji: '🐙', genre: 'Cosmic Horror', systemId: 'coc' },
  { id: 'startrek', label: 'Star Trek Adventures', emoji: '🖖', genre: 'Science Fiction', systemId: 'startrek' },
  { id: 'sotdl', label: 'Shadow of the Demon Lord', emoji: '💀', genre: 'Dark Fantasy', systemId: 'sotdl' },
  { id: 'wfrp', label: 'Warhammer Fantasy', emoji: '🐺', genre: 'Grimdark', systemId: 'wfrp' },
  { id: 'alien', label: 'Alien RPG', emoji: '🎃', genre: 'Sci-Fi Horror', systemId: 'alien' },
  { id: 'shadowrun', label: 'Shadowrun', emoji: '🌆', genre: 'Cyberpunk Fantasy', systemId: 'shadowrun' },
  { id: 'swse', label: 'Star Wars Saga', emoji: '⚡', genre: 'Space Opera', systemId: 'swse' },
  { id: 'osr', label: 'OSR / Old-School', emoji: '🕯️', genre: 'Classic Dungeon Crawl' },
  { id: 'custom', label: 'Custom / Homebrew', emoji: '✨', genre: 'Any genre you like' },
]

// ─────────────────────────────────────────────
// Tone / genre label maps for the mood display
// ─────────────────────────────────────────────

const TONE_LABELS: Record<string, string> = {
  heroic: '⚔️ Heroic',
  grim: '🌑 Grim',
  horror: '💀 Horror',
  comedy: '🎭 Comedy',
  thriller: '🕵️ Thriller',
  political: '👑 Political Intrigue',
}

const GENRE_LABELS: Record<string, string> = {
  fantasy: '🏰 Fantasy',
  horror: '🐙 Horror',
  'sci-fi': '🚀 Sci-Fi',
  mystery: '🔍 Mystery',
  thriller: '🕵️ Thriller',
  political: '👑 Political',
  'post-apocalyptic': '🌋 Post-Apocalyptic',
}

const PACING_LABELS: Record<string, string> = {
  fast: '⚡ Fast-Paced',
  moderate: '🕰️ Moderate',
  slow: '🌘 Slow Burn',
}

// ─────────────────────────────────────────────
// Progress indicator
// ─────────────────────────────────────────────

function WizardProgress({ steps, current }: { steps: Step[]; current: Step }) {
  const currentIdx = steps.indexOf(current)
  return (
    <div className="wizard-progress">
      {steps.map((step, i) => {
        const isDone = i < currentIdx
        const isActive = i === currentIdx
        return (
          <React.Fragment key={step}>
            {i > 0 && (
              <div className={`wizard-progress-line${isDone ? ' wizard-progress-line--done' : ''}`} />
            )}
            <div
              className={`wizard-progress-dot${isActive ? ' wizard-progress-dot--active' : isDone ? ' wizard-progress-dot--done' : ''}`}
              title={STEP_LABELS[step]}
            >
              {isDone ? '✓' : i + 1}
            </div>
          </React.Fragment>
        )
      })}
    </div>
  )
}

// ─────────────────────────────────────────────
// Quiz step — one question at a time
// ─────────────────────────────────────────────

function StepQuiz({
  draft,
  questionIndex,
  onAnswer,
}: {
  draft: CampaignDraft
  questionIndex: number
  onAnswer: (qId: string, optionId: string) => void
}) {
  const question = CAMPAIGN_QUIZ[questionIndex]
  if (!question) return null

  const total = CAMPAIGN_QUIZ.length
  const currentAnswer = draft.quizAnswers[question.id]

  return (
    <div className="wizard-body">
      <div>
        <div className="wizard-step-heading">The Adventure Begins…</div>
        <div className="wizard-step-sub">
          Scene {questionIndex + 1} of {total} — your choices shape the campaign
        </div>
      </div>
      <div className="wizard-scenario-card">
        <div className="wizard-scenario-scene">{question.scene}</div>
        <div className="wizard-scenario-prompt">{question.prompt}</div>
        <div className="wizard-answer-list">
          {question.options.map((opt, idx) => (
            <button
              key={opt.id}
              type="button"
              className={`wizard-answer-btn${currentAnswer === opt.id ? ' is-selected' : ''}`}
              onClick={() => onAnswer(question.id, opt.id)}
            >
              <span className="wizard-answer-emoji">{opt.emoji}</span>
              <span>
                <strong style={{ marginRight: 6 }}>{String.fromCharCode(65 + idx)}.</strong>
                {opt.text}
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────
// Name step
// ─────────────────────────────────────────────

function StepName({
  draft,
  derived,
  onNameChange,
  onWorldNameChange,
}: {
  draft: CampaignDraft
  derived: ReturnType<typeof deriveCampaignSettings>
  onNameChange: (v: string) => void
  onWorldNameChange: (v: string) => void
}) {
  const toneName = TONE_LABELS[derived.tone] ?? derived.tone
  const genreName = GENRE_LABELS[derived.genre] ?? derived.genre

  const randomizeName = useCallback(() => {
    const pick = RANDOM_CAMPAIGN_NAMES[Math.floor(Math.random() * RANDOM_CAMPAIGN_NAMES.length)]
    onNameChange(pick)
  }, [onNameChange])

  return (
    <div className="wizard-body">
      <div>
        <div className="wizard-step-heading">Name your campaign</div>
        <div className="wizard-step-sub">
          Based on your choices, this feels like a <strong>{toneName}</strong> {genreName} adventure.
        </div>
      </div>
      <div className="stack" style={{ gap: 16 }}>
        <div className="stack" style={{ gap: 6 }}>
          <label style={{ fontSize: 12, color: 'var(--muted-text)', fontWeight: 600 }}>
            Campaign Name
          </label>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              className="wizard-name-input"
              type="text"
              value={draft.name}
              onChange={(e) => onNameChange(e.target.value)}
              placeholder="e.g. The Shattered Crown"
              autoFocus
              maxLength={100}
              style={{ flex: 1 }}
            />
            <button
              type="button"
              className="btn btn-secondary"
              onClick={randomizeName}
              title="Random campaign name"
              style={{ flexShrink: 0, fontSize: 18, padding: '6px 12px', lineHeight: 1 }}
            >
              &#x21BA;
            </button>
          </div>
        </div>
        <div className="stack" style={{ gap: 6 }}>
          <label style={{ fontSize: 12, color: 'var(--muted-text)', fontWeight: 600 }}>
            World Name <span style={{ fontWeight: 400 }}>(optional)</span>
          </label>
          <input
            className="input"
            type="text"
            value={draft.worldName}
            onChange={(e) => onWorldNameChange(e.target.value)}
            placeholder="e.g. Eldervale, The Outer Spiral, Golarion…"
            maxLength={80}
          />
          <div className="muted" style={{ fontSize: 11 }}>
            Leave blank to decide later or let TavernTails suggest one when the first scene generates.
          </div>
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────
// Ruleset step
// ─────────────────────────────────────────────

function StepRuleset({
  draft,
  onSelect,
}: {
  draft: CampaignDraft
  onSelect: (id: string) => void
}) {
  return (
    <div className="wizard-body">
      <div>
        <div className="wizard-step-heading">Game System</div>
        <div className="wizard-step-sub">Which ruleset are you running?</div>
      </div>
      <div className="wizard-option-grid wizard-option-grid--wide">
        {RULESET_OPTIONS.map((opt) => (
          <button
            key={opt.id}
            type="button"
            className={`wizard-option-card${draft.ruleset === opt.id ? ' is-selected' : ''}`}
            onClick={() => onSelect(opt.id)}
          >
            <span className="wizard-option-emoji">{opt.emoji}</span>
            <span className="wizard-option-name">{opt.label}</span>
            <span className="wizard-option-desc">{opt.genre}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────
// Level step
// ─────────────────────────────────────────────

function StepLevel({
  draft,
  onLevelChange,
}: {
  draft: CampaignDraft
  onLevelChange: (v: number) => void
}) {
  const levelDescriptions: Record<number, string> = {
    1: 'Fresh adventurers — humble origins, big dreams.',
    3: 'Capable heroes with a defining feature unlocked.',
    5: 'True adventurers — the world starts to notice you.',
    7: 'Seasoned veterans with real power.',
    10: 'Renowned heroes — factions and powers take interest.',
    13: 'Paragons — you can reshape regions.',
    17: 'Legends — cosmic-tier threats are your problem now.',
    20: 'Mythic — you stand among the greatest who have ever lived.',
  }

  const getDesc = (level: number) => {
    const keys = Object.keys(levelDescriptions).map(Number).sort((a, b) => a - b)
    for (let i = keys.length - 1; i >= 0; i--) {
      if (level >= keys[i]) return levelDescriptions[keys[i]]
    }
    return levelDescriptions[1]
  }

  return (
    <div className="wizard-body">
      <div>
        <div className="wizard-step-heading">Starting Level</div>
        <div className="wizard-step-sub">Where does your campaign begin?</div>
      </div>
      <div className="card card-pad stack" style={{ gap: 14 }}>
        <div className="wizard-level-track">
          <span style={{ fontSize: 12, color: 'var(--muted-text)' }}>1</span>
          <input
            type="range"
            className="wizard-level-slider"
            min={1}
            max={20}
            value={draft.startingLevel}
            onChange={(e) => onLevelChange(Number(e.target.value))}
          />
          <span style={{ fontSize: 12, color: 'var(--muted-text)' }}>20</span>
          <span className="wizard-level-badge">{draft.startingLevel}</span>
        </div>
        <div className="muted" style={{ fontSize: 13, fontStyle: 'italic' }}>
          {getDesc(draft.startingLevel)}
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────
// Review step
// ─────────────────────────────────────────────

function StepReview({
  draft,
  derived,
  onJumpTo,
  onSubmit,
  busy,
  error,
}: {
  draft: CampaignDraft
  derived: ReturnType<typeof deriveCampaignSettings>
  onJumpTo: (step: Step) => void
  onSubmit: () => void
  busy: boolean
  error: string | null
}) {
  const moodTags = [
    TONE_LABELS[derived.tone],
    GENRE_LABELS[derived.genre],
    PACING_LABELS[derived.pacing],
  ].filter(Boolean)

  const ruleset = RULESET_OPTIONS.find((r) => r.id === draft.ruleset)
  const missingName = !draft.name.trim()
  const missingRuleset = !draft.ruleset

  return (
    <div className="wizard-body">
      <div>
        <div className="wizard-step-heading">Ready to adventure?</div>
        <div className="wizard-step-sub">Review and confirm your campaign settings.</div>
      </div>

      <div className="card card-pad stack" style={{ gap: 10 }}>
        <div className="card-section-header">Campaign Mood</div>
        <div className="wizard-mood-tags">
          {moodTags.map((tag) => (
            <span key={tag} className="wizard-mood-tag">{tag}</span>
          ))}
        </div>
        <div className="muted" style={{ fontSize: 12, fontStyle: 'italic' }}>
          {derived.setting_summary}
        </div>
      </div>

      <div className="wizard-review-grid">
        <div className="wizard-review-row">
          <span className="wizard-review-label">Campaign Name</span>
          <span className="wizard-review-value" style={{ color: missingName ? 'var(--error, #e05a5a)' : undefined }}>
            {draft.name || '(required — go to Name step)'}
          </span>
          <button className="wizard-review-edit" onClick={() => onJumpTo('name')}>Edit</button>
        </div>
        {draft.worldName && (
          <div className="wizard-review-row">
            <span className="wizard-review-label">World</span>
            <span className="wizard-review-value">{draft.worldName}</span>
            <button className="wizard-review-edit" onClick={() => onJumpTo('name')}>Edit</button>
          </div>
        )}
        <div className="wizard-review-row">
          <span className="wizard-review-label">Ruleset</span>
          <span className="wizard-review-value" style={{ color: missingRuleset ? 'var(--error, #e05a5a)' : undefined }}>
            {ruleset ? `${ruleset.emoji} ${ruleset.label}` : '(required — go to System step)'}
          </span>
          <button className="wizard-review-edit" onClick={() => onJumpTo('ruleset')}>Edit</button>
        </div>
        <div className="wizard-review-row">
          <span className="wizard-review-label">Starting Level</span>
          <span className="wizard-review-value">{draft.startingLevel}</span>
          <button className="wizard-review-edit" onClick={() => onJumpTo('level')}>Edit</button>
        </div>
        <div className="wizard-review-row">
          <span className="wizard-review-label">Tone</span>
          <span className="wizard-review-value">{TONE_LABELS[derived.tone] ?? derived.tone}</span>
          <button className="wizard-review-edit" onClick={() => onJumpTo('quiz')}>Re-quiz</button>
        </div>
      </div>

      {error && (
        <div className="inline-alert inline-alert-error">{error}</div>
      )}

      <button
        className="btn"
        type="button"
        disabled={busy || missingName || missingRuleset}
        onClick={onSubmit}
        style={{ alignSelf: 'flex-start' }}
      >
        {busy ? 'Creating…' : 'Create Campaign'}
      </button>
    </div>
  )
}

// ─────────────────────────────────────────────
// Main wizard
// ─────────────────────────────────────────────

type Props = {
  onDone: () => void
  onCampaignCreated?: (campaignId: string) => void
}

export default function CampaignCreationWizard({ onDone, onCampaignCreated }: Props) {
  const [draft, setDraft] = useState<CampaignDraft>({ ...EMPTY_DRAFT })
  const [step, setStep] = useState<Step>('quiz')
  const [quizIndex, setQuizIndex] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const stepIdx = STEPS.indexOf(step)
  const derived = deriveCampaignSettings(draft.quizAnswers)

  // ── Navigation ──────────────────────────────
  function goNext() {
    const next = STEPS[stepIdx + 1]
    if (next) setStep(next)
  }

  function goBack() {
    if (step === 'quiz' && quizIndex > 0) {
      setQuizIndex(quizIndex - 1)
      return
    }
    const prev = STEPS[stepIdx - 1]
    if (prev) setStep(prev)
  }

  function jumpTo(target: Step) {
    setStep(target)
    if (target === 'quiz') setQuizIndex(0)
  }

  // ── Quiz flow ───────────────────────────────
  function answerQuiz(qId: string, optionId: string) {
    setDraft((d) => ({ ...d, quizAnswers: { ...d.quizAnswers, [qId]: optionId } }))
    const isLast = quizIndex >= CAMPAIGN_QUIZ.length - 1
    if (isLast) {
      goNext()
    } else {
      setQuizIndex(quizIndex + 1)
    }
  }

  // ── Submit ──────────────────────────────────
  async function submit() {
    if (!draft.name.trim()) {
      setError('Please enter a campaign name.')
      return
    }
    if (!draft.ruleset) {
      setError('Please select a game system.')
      return
    }

    setBusy(true)
    setError(null)
    try {
      // 1. Create the campaign
      const createRes = await apiFetch('/campaigns', {
        method: 'POST',
        body: JSON.stringify({
          name: draft.name.trim(),
          description: derived.setting_summary,
        }),
      })
      if (!createRes.ok) {
        const err = await createRes.json().catch(() => null)
        throw new Error(err?.detail || 'Failed to create campaign')
      }
      const body = await createRes.json()
      const campaign = body?.campaign ?? body
      const cid = campaign?.id ?? campaign?.campaign_id

      if (!cid) throw new Error('Campaign created but ID not returned')

      // 2. Apply settings
      const settingsRes = await apiFetch(`/campaigns/${cid}/settings`, {
        method: 'PUT',
        body: JSON.stringify({
          world_name: draft.worldName.trim() || '',
          setting_summary: derived.setting_summary,
          tone: derived.tone,
          ruleset: draft.ruleset,
          starting_level: draft.startingLevel,
          house_rules: '',
        }),
      })
      if (!settingsRes.ok) {
        const err = await settingsRes.json().catch(() => null)
        throw new Error(err?.detail || 'Campaign created but settings failed to save')
      }

      onCampaignCreated?.(cid)
      onDone()
    } catch (e: any) {
      setError(e?.message || 'Something went wrong. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  // ── Can advance? ────────────────────────────
  function canAdvance(): boolean {
    switch (step) {
      case 'quiz': return Boolean(draft.quizAnswers[CAMPAIGN_QUIZ[quizIndex]?.id ?? ''])
      case 'name': return Boolean(draft.name.trim())
      case 'ruleset': return Boolean(draft.ruleset)
      default: return true
    }
  }

  return (
    <section className="dashboard-panel stack">
      <PageHeader
        title="New Campaign"
        subtitle="Answer a few quick scenarios and we'll build a campaign tailored to your style."
        actions={
          <button className="btn btn-quiet" type="button" onClick={onDone}>
            Cancel
          </button>
        }
      />

      <WizardProgress steps={STEPS} current={step} />

      <div className="card card-pad" style={{ maxWidth: 680 }}>
        {step === 'quiz' && (
          <StepQuiz
            draft={draft}
            questionIndex={quizIndex}
            onAnswer={answerQuiz}
          />
        )}

        {step === 'name' && (
          <StepName
            draft={draft}
            derived={derived}
            onNameChange={(v) => setDraft((d) => ({ ...d, name: v }))}
            onWorldNameChange={(v) => setDraft((d) => ({ ...d, worldName: v }))}
          />
        )}

        {step === 'ruleset' && (
          <StepRuleset
            draft={draft}
            onSelect={(id) => {
              setDraft((d) => ({ ...d, ruleset: id }))
              goNext()
            }}
          />
        )}

        {step === 'level' && (
          <StepLevel
            draft={draft}
            onLevelChange={(v) => setDraft((d) => ({ ...d, startingLevel: v }))}
          />
        )}

        {step === 'review' && (
          <StepReview
            draft={draft}
            derived={derived}
            onJumpTo={jumpTo}
            onSubmit={submit}
            busy={busy}
            error={error}
          />
        )}

        {/* Navigation buttons */}
        {step !== 'review' && step !== 'quiz' && step !== 'ruleset' && (
          <div className="wizard-nav" style={{ marginTop: 16 }}>
            <button className="btn btn-secondary" type="button" onClick={goBack}>
              ← Back
            </button>
            <button className="btn" type="button" disabled={!canAdvance()} onClick={goNext}>
              Next →
            </button>
          </div>
        )}

        {(step === 'quiz' || step === 'ruleset') && (
          <div className="wizard-nav" style={{ marginTop: 16, justifyContent: 'flex-start' }}>
            <button className="btn btn-secondary" type="button" onClick={goBack}>
              ← Back
            </button>
          </div>
        )}

        {step === 'review' && (
          <div className="wizard-nav" style={{ marginTop: 8 }}>
            <button className="btn btn-secondary" type="button" onClick={goBack}>
              ← Back
            </button>
          </div>
        )}
      </div>
    </section>
  )
}
