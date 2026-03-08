import React, { useCallback, useEffect, useMemo, useState } from 'react'

import { apiFetch } from '../../api'
import PageHeader from '../ui/PageHeader'
import './CharacterWizardView.css'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type AbilityScore = { key: string; label: string }

type WizardChoice = {
  id: string
  text: string
  skills: string[]
  narrative: string
  background?: string
  languages?: string
}

type WizardQuestion = {
  id: string
  text: string
  choices: WizardChoice[]
}

type SystemConfig = {
  name: string
  publisher: string
  classes: string[]
  ability_scores: AbilityScore[]
  standard_array: number[]
  point_buy_budget: number
  point_buy_min: number
  point_buy_max: number
  questions: WizardQuestion[]
}

type WizardStep =
  | 'system'
  | 'basics'
  | 'abilities'
  | 'mode'
  | 'questionnaire'
  | 'manual'
  | 'review'

// D&D 5e point-buy cost table
const DND5E_POINT_COSTS: Record<number, number> = {
  8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9,
}

type Props = {
  activeSessionId: string | null
  onRefreshCharacters: () => Promise<void>
  onAssignCharacterToSession: (characterId: number | null) => Promise<void>
  onSetActiveCharacterId: (characterId: number | null) => void
  onDone: () => void
  onGoToGameplay: () => void
  notificationsPending?: boolean
  onNotificationsClick?: () => void
}

export default function CharacterWizardView({
  activeSessionId,
  onRefreshCharacters,
  onAssignCharacterToSession,
  onSetActiveCharacterId,
  onDone,
  onGoToGameplay,
}: Props) {
  // ---------------------------------------------------------------------------
  // Config loading
  // ---------------------------------------------------------------------------
  const [systems, setSystems] = useState<SystemConfig[]>([])
  const [configError, setConfigError] = useState<string | null>(null)

  useEffect(() => {
    apiFetch('/characters/wizard/config')
      .then((r) => r.json())
      .then((d) => setSystems(d.systems ?? []))
      .catch(() => setConfigError('Could not load wizard configuration.'))
  }, [])

  // ---------------------------------------------------------------------------
  // Wizard state
  // ---------------------------------------------------------------------------
  const [step, setStep] = useState<WizardStep>('system')

  // Step 1
  const [gameSystem, setGameSystem] = useState('')

  // Step 2
  const [name, setName] = useState('')
  const [characterClass, setCharacterClass] = useState('')
  const [level, setLevel] = useState(1)

  // Step 3 — ability scores
  const [abilityMethod, setAbilityMethod] = useState<'standard-array' | 'point-buy'>('standard-array')
  // standard-array: maps ability key -> assigned value (null = unassigned)
  const [arrayAssignments, setArrayAssignments] = useState<Record<string, number | null>>({})
  // point-buy: maps ability key -> current value
  const [pointBuyValues, setPointBuyValues] = useState<Record<string, number>>({})

  // Step 4
  const [creationMode, setCreationMode] = useState<'helper' | 'manual'>('helper')

  // Step 5a — questionnaire
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [questionIndex, setQuestionIndex] = useState(0)

  // Step 5b — manual
  const [manualSkills, setManualSkills] = useState('')
  const [manualBackground, setManualBackground] = useState('')
  const [manualLanguages, setManualLanguages] = useState('')
  const [manualBackstory, setManualBackstory] = useState('')
  const [manualEquipment, setManualEquipment] = useState('')

  // Step 6 — review editable fields
  const [reviewName, setReviewName] = useState('')
  const [reviewClass, setReviewClass] = useState('')
  const [reviewLevel, setReviewLevel] = useState(1)
  const [reviewBackstory, setReviewBackstory] = useState('')
  const [reviewBackground, setReviewBackground] = useState('')
  const [reviewLanguages, setReviewLanguages] = useState('')
  const [reviewSkills, setReviewSkills] = useState('')
  const [reviewEquipment, setReviewEquipment] = useState('')

  // Save state
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  // ---------------------------------------------------------------------------
  // Derived values
  // ---------------------------------------------------------------------------
  const systemConfig = useMemo(
    () => systems.find((s) => s.name === gameSystem) ?? null,
    [systems, gameSystem],
  )

  // Compute final ability scores
  const finalAbilityScores = useMemo<Record<string, number>>(() => {
    if (!systemConfig) return {}
    if (abilityMethod === 'standard-array') {
      const result: Record<string, number> = {}
      for (const score of systemConfig.ability_scores) {
        const val = arrayAssignments[score.key]
        if (val != null) result[score.key] = val
      }
      return result
    }
    return { ...pointBuyValues }
  }, [systemConfig, abilityMethod, arrayAssignments, pointBuyValues])

  // Derive skills from questionnaire answers (deduplicated)
  const derivedSkills = useMemo<string[]>(() => {
    if (!systemConfig) return []
    const skillSet = new Set<string>()
    for (const [qId, cId] of Object.entries(answers)) {
      const question = systemConfig.questions.find((q) => q.id === qId)
      const choice = question?.choices.find((c) => c.id === cId)
      choice?.skills.forEach((s) => skillSet.add(s))
    }
    return Array.from(skillSet)
  }, [answers, systemConfig])

  // Derive backstory from questionnaire answers
  const derivedBackstory = useMemo<string>(() => {
    if (!systemConfig) return ''
    const fragments: string[] = []
    for (const [qId, cId] of Object.entries(answers)) {
      const question = systemConfig.questions.find((q) => q.id === qId)
      const choice = question?.choices.find((c) => c.id === cId)
      if (choice?.narrative) fragments.push(choice.narrative)
    }
    return fragments.join(' ')
  }, [answers, systemConfig])

  // Derive background from last question answer
  const derivedBackground = useMemo<string>(() => {
    if (!systemConfig) return ''
    const lastQ = systemConfig.questions[systemConfig.questions.length - 1]
    if (!lastQ) return ''
    const choiceId = answers[lastQ.id]
    if (!choiceId) return ''
    return lastQ.choices.find((c) => c.id === choiceId)?.background ?? ''
  }, [answers, systemConfig])

  // Derive languages from last question answer
  const derivedLanguages = useMemo<string>(() => {
    if (!systemConfig) return ''
    const lastQ = systemConfig.questions[systemConfig.questions.length - 1]
    if (!lastQ) return ''
    const choiceId = answers[lastQ.id]
    if (!choiceId) return ''
    return lastQ.choices.find((c) => c.id === choiceId)?.languages ?? ''
  }, [answers, systemConfig])

  // Point-buy spending
  const pointBuySpent = useMemo<number>(() => {
    if (!systemConfig) return 0
    return Object.values(pointBuyValues).reduce((sum, v) => {
      const isDnd5e = systemConfig.name === 'D&D 5e'
      const baseCost = Math.max(0, v - systemConfig.point_buy_min)
      const cost = isDnd5e ? (DND5E_POINT_COSTS[v] ?? baseCost) : baseCost
      return sum + cost
    }, 0)
  }, [pointBuyValues, systemConfig])

  const pointBuyRemaining = useMemo(() => {
    if (!systemConfig) return 0
    return systemConfig.point_buy_budget - pointBuySpent
  }, [systemConfig, pointBuySpent])

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------
  const initAbilities = useCallback(
    (config: SystemConfig) => {
      const arr: Record<string, number | null> = {}
      const pb: Record<string, number> = {}
      for (const score of config.ability_scores) {
        arr[score.key] = null
        pb[score.key] = config.point_buy_min
      }
      setArrayAssignments(arr)
      setPointBuyValues(pb)
    },
    [],
  )

  const goToReview = useCallback(() => {
    const isHelper = creationMode === 'helper'
    setReviewName(name)
    setReviewClass(characterClass)
    setReviewLevel(level)
    setReviewBackstory(isHelper ? derivedBackstory : manualBackstory)
    setReviewBackground(isHelper ? derivedBackground : manualBackground)
    setReviewLanguages(isHelper ? derivedLanguages : manualLanguages)
    setReviewSkills(isHelper ? derivedSkills.join(', ') : manualSkills)
    setReviewEquipment(manualEquipment)
    setStep('review')
  }, [
    creationMode, name, characterClass, level,
    derivedBackstory, manualBackstory,
    derivedBackground, manualBackground,
    derivedLanguages, manualLanguages,
    derivedSkills, manualSkills,
    manualEquipment,
  ])

  async function save(andPlay: boolean) {
    setSaving(true)
    setSaveError(null)
    try {
      const skillsArray = reviewSkills
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
        .map((s) => ({ name: s }))

      const sheet: Record<string, unknown> = {
        game_system: gameSystem,
        stats: finalAbilityScores,
        skills: skillsArray,
        background: reviewBackground,
        languages: reviewLanguages,
        backstory: reviewBackstory,
        created_via: 'wizard',
      }
      if (reviewEquipment.trim()) {
        sheet.equipment = reviewEquipment.trim()
      }

      const res = await apiFetch('/characters', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: reviewName.trim(),
          level: Math.max(1, Math.min(20, reviewLevel)),
          class_name: reviewClass.trim() || null,
          sheet,
        }),
      })

      if (res.ok) {
        const data = await res.json().catch(() => ({}))
        const createdId: number | null =
          typeof data?.character?.id === 'number' ? data.character.id : null
        await onRefreshCharacters()
        if (andPlay && createdId != null) {
          onSetActiveCharacterId(createdId)
          if (activeSessionId) {
            await onAssignCharacterToSession(createdId)
          }
          onGoToGameplay()
        } else {
          if (createdId != null) onSetActiveCharacterId(createdId)
          onDone()
        }
      } else {
        const err = await res.json().catch(() => ({}))
        setSaveError(err?.detail ?? 'Failed to create character.')
      }
    } catch (err) {
      setSaveError('A network error occurred. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  // ---------------------------------------------------------------------------
  // Step renderers — "Tome of Origins" parchment aesthetic
  // ---------------------------------------------------------------------------

  const STEP_TRAIL: { key: WizardStep; label: string }[] = [
    { key: 'system',       label: 'System' },
    { key: 'basics',       label: 'Basics' },
    { key: 'abilities',    label: 'Abilities' },
    { key: 'mode',         label: 'Mode' },
    { key: creationMode === 'helper' ? 'questionnaire' : 'manual',
      label: creationMode === 'helper' ? 'Tome' : 'Details' },
    { key: 'review',       label: 'Review' },
  ]

  function renderStepIndicator() {
    const activeIdx = STEP_TRAIL.findIndex((s) => s.key === step)
    return (
      <div className="wiz-step-trail" role="navigation" aria-label="Wizard steps">
        {STEP_TRAIL.map(({ key, label }, i) => {
          const isActive = i === activeIdx
          const isDone   = i < activeIdx
          return (
            <div key={key} className="wiz-trail-item">
              <div className="wiz-trail-dot">
                <div className={`wiz-trail-gem${isActive ? ' is-active' : isDone ? ' is-done' : ''}`}>
                  {isDone ? '✓' : i + 1}
                </div>
                <span className={`wiz-trail-label${isActive ? ' is-active' : isDone ? ' is-done' : ''}`}>
                  {label}
                </span>
              </div>
              {i < STEP_TRAIL.length - 1 && <div className="wiz-trail-line" />}
            </div>
          )
        })}
      </div>
    )
  }

  // ---- System ----
  function renderSystemStep() {
    return (
      <div className="wiz-card" style={{ maxWidth: 600 }}>
        <div className="wiz-card-eyebrow">Step I — Origin</div>
        <h2 className="wiz-card-title">Choose a Game System</h2>
        <p className="wiz-card-subtitle">
          Select the tabletop RPG system this character is built for. The wizard will adapt
          classes, ability scores, and lore questions to match your choice.
        </p>
        <div className="wiz-divider"><div className="wiz-divider-line"/><div className="wiz-divider-gem"/><div className="wiz-divider-line"/></div>

        {configError && <div className="wiz-error">{configError}</div>}

        <div className="wiz-system-grid wiz-gap-md">
          {systems.map((sys) => (
            <button
              key={sys.name}
              type="button"
              className={`wiz-system-chip${gameSystem === sys.name ? ' is-selected' : ''}`}
              onClick={() => setGameSystem(sys.name)}
            >
              <span className="wiz-chip-name">{sys.name}</span>
              <span className="wiz-chip-pub">{sys.publisher}</span>
            </button>
          ))}
        </div>

        <div className="wiz-nav">
          <div className="wiz-nav-left">
            <button className="wiz-btn-back" type="button" onClick={onDone}>Cancel</button>
          </div>
          <div className="wiz-nav-right">
            <button
              className="wiz-btn-next"
              type="button"
              disabled={!gameSystem}
              onClick={() => { if (systemConfig) initAbilities(systemConfig); setStep('basics') }}
            >
              Continue →
            </button>
          </div>
        </div>
      </div>
    )
  }

  // ---- Basics ----
  function renderBasicsStep() {
    const classes = systemConfig?.classes ?? []
    return (
      <div className="wiz-card" style={{ maxWidth: 520 }}>
        <div className="wiz-card-eyebrow">Step II — Identity</div>
        <h2 className="wiz-card-title">Who Is Your Character?</h2>
        <p className="wiz-card-subtitle">
          Give your hero a name, choose their class, and set their starting level.
        </p>
        <div className="wiz-divider"><div className="wiz-divider-line"/><div className="wiz-divider-gem"/><div className="wiz-divider-line"/></div>

        <div className="wiz-field">
          <span className="wiz-label">Name *</span>
          <input
            className="wiz-input"
            placeholder="Enter character name…"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>

        <div className="wiz-field">
          <span className="wiz-label">Class</span>
          {classes.length > 0 ? (
            <select
              className="wiz-select"
              value={characterClass}
              onChange={(e) => setCharacterClass(e.target.value)}
            >
              <option value="">— Select class —</option>
              {classes.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          ) : (
            <input
              className="wiz-input"
              placeholder="Class (optional)"
              value={characterClass}
              onChange={(e) => setCharacterClass(e.target.value)}
            />
          )}
        </div>

        <div className="wiz-field">
          <span className="wiz-label">Starting Level</span>
          <input
            className="wiz-input wiz-input-sm"
            type="number"
            min={1}
            max={20}
            value={level}
            onChange={(e) => setLevel(Math.max(1, Math.min(20, Number(e.target.value) || 1)))}
          />
        </div>

        <div className="wiz-nav">
          <div className="wiz-nav-left">
            <button className="wiz-btn-back" type="button" onClick={() => setStep('system')}>← Back</button>
          </div>
          <div className="wiz-nav-right">
            <button
              className="wiz-btn-next"
              type="button"
              disabled={!name.trim()}
              onClick={() => setStep('abilities')}
            >
              Continue →
            </button>
          </div>
        </div>
      </div>
    )
  }

  // ---- Abilities ----
  function renderAbilitiesStep() {
    const config = systemConfig
    if (!config) return null
    const unassigned = config.standard_array.filter(
      (v) => !Object.values(arrayAssignments).includes(v),
    )
    return (
      <div className="wiz-card" style={{ maxWidth: 580 }}>
        <div className="wiz-card-eyebrow">Step III — Attributes</div>
        <h2 className="wiz-card-title">Ability Scores</h2>
        <p className="wiz-card-subtitle">
          Every hero is defined by six core attributes. Choose how to set yours.
        </p>
        <div className="wiz-divider"><div className="wiz-divider-line"/><div className="wiz-divider-gem"/><div className="wiz-divider-line"/></div>

        <div className="wiz-method-tabs wiz-gap-md">
          <button
            type="button"
            className={`wiz-method-tab${abilityMethod === 'standard-array' ? ' is-active' : ''}`}
            onClick={() => setAbilityMethod('standard-array')}
          >
            Standard Array
          </button>
          {config.point_buy_budget > 0 && (
            <button
              type="button"
              className={`wiz-method-tab${abilityMethod === 'point-buy' ? ' is-active' : ''}`}
              onClick={() => setAbilityMethod('point-buy')}
            >
              Point Buy
            </button>
          )}
        </div>

        {abilityMethod === 'standard-array' && (
          <>
            <p className="wiz-hint">
              Assign each value from [{config.standard_array.join(', ')}] to one ability.
            </p>
            <div className="wiz-ability-grid wiz-gap-md">
              {config.ability_scores.map((score) => (
                <div key={score.key} className="wiz-ability-row">
                  <span className="wiz-ability-label">{score.label}</span>
                  <select
                    className="wiz-select"
                    style={{ maxWidth: 110 }}
                    value={arrayAssignments[score.key] ?? ''}
                    onChange={(e) => {
                      const newVal = e.target.value === '' ? null : Number(e.target.value)
                      setArrayAssignments((prev) => {
                        const next = { ...prev }
                        if (newVal != null) {
                          for (const k of Object.keys(next)) {
                            if (next[k] === newVal && k !== score.key) next[k] = null
                          }
                        }
                        next[score.key] = newVal
                        return next
                      })
                    }}
                  >
                    <option value="">— pick —</option>
                    {config.standard_array.map((v) => {
                      const taken = Object.entries(arrayAssignments).some(
                        ([k, vv]) => vv === v && k !== score.key,
                      )
                      return (
                        <option key={v} value={v} disabled={taken}>
                          {v}{taken ? ' (taken)' : ''}
                        </option>
                      )
                    })}
                  </select>
                  {arrayAssignments[score.key] != null && (
                    <span className="wiz-ability-value">{arrayAssignments[score.key]}</span>
                  )}
                </div>
              ))}
            </div>
            {unassigned.length > 0 && (
              <p className="wiz-hint">Unassigned: [{unassigned.join(', ')}]</p>
            )}
          </>
        )}

        {abilityMethod === 'point-buy' && (
          <>
            <p className="wiz-hint">
              Budget: <strong>{config.point_buy_budget}</strong> points — remaining:{' '}
              <strong>{pointBuyRemaining}</strong>. Each ability starts at {config.point_buy_min}.
            </p>
            <div className="wiz-ability-grid wiz-gap-md">
              {config.ability_scores.map((score) => {
                const val = pointBuyValues[score.key] ?? config.point_buy_min
                const canIncrease = val < config.point_buy_max && pointBuyRemaining > 0
                const canDecrease = val > config.point_buy_min
                return (
                  <div key={score.key} className="wiz-ability-row">
                    <span className="wiz-ability-label">{score.label}</span>
                    <button
                      type="button"
                      className="wiz-ability-btn"
                      disabled={!canDecrease}
                      onClick={() => setPointBuyValues((prev) => ({ ...prev, [score.key]: val - 1 }))}
                    >−</button>
                    <span className="wiz-ability-value">{val}</span>
                    <button
                      type="button"
                      className="wiz-ability-btn"
                      disabled={!canIncrease}
                      onClick={() => setPointBuyValues((prev) => ({ ...prev, [score.key]: val + 1 }))}
                    >+</button>
                  </div>
                )
              })}
            </div>
          </>
        )}

        <div className="wiz-nav">
          <div className="wiz-nav-left">
            <button className="wiz-btn-back" type="button" onClick={() => setStep('basics')}>← Back</button>
          </div>
          <div className="wiz-nav-right">
            <button className="wiz-btn-next" type="button" onClick={() => setStep('mode')}>Continue →</button>
          </div>
        </div>
      </div>
    )
  }

  // ---- Mode ----
  function renderModeStep() {
    return (
      <div className="wiz-card" style={{ maxWidth: 560 }}>
        <div className="wiz-card-eyebrow">Step IV — Path</div>
        <h2 className="wiz-card-title">Choose Your Path</h2>
        <p className="wiz-card-subtitle">
          How would you like to shape your character's history, skills, and purpose?
        </p>
        <div className="wiz-divider"><div className="wiz-divider-line"/><div className="wiz-divider-gem"/><div className="wiz-divider-line"/></div>

        <div className="wiz-mode-grid wiz-gap-md">
          <button
            type="button"
            className={`wiz-mode-card${creationMode === 'helper' ? ' is-selected' : ''}`}
            onClick={() => setCreationMode('helper')}
          >
            <span className="wiz-mode-title">📜 The Tome — Guided Questionnaire</span>
            <span className="wiz-mode-desc">
              Answer a short series of scenario questions drawn from the old book of origins.
              Your choices weave a backstory and determine your proficiencies.
            </span>
          </button>
          <button
            type="button"
            className={`wiz-mode-card${creationMode === 'manual' ? ' is-selected' : ''}`}
            onClick={() => setCreationMode('manual')}
          >
            <span className="wiz-mode-title">✒ Scribe's Quill — Full Manual Control</span>
            <span className="wiz-mode-desc">
              Write your character's history directly. Choose every skill, language, and
              background trait by hand.
            </span>
          </button>
        </div>

        <div className="wiz-nav">
          <div className="wiz-nav-left">
            <button className="wiz-btn-back" type="button" onClick={() => setStep('abilities')}>← Back</button>
          </div>
          <div className="wiz-nav-right">
            <button
              className="wiz-btn-next"
              type="button"
              onClick={() => {
                setAnswers({})
                setQuestionIndex(0)
                setStep(creationMode === 'helper' ? 'questionnaire' : 'manual')
              }}
            >
              Continue →
            </button>
          </div>
        </div>
      </div>
    )
  }

  // ---- Questionnaire (full Tome treatment) ----
  function renderQuestionnaireStep() {
    const questions = systemConfig?.questions ?? []
    if (questions.length === 0) {
      return (
        <div className="wiz-card" style={{ maxWidth: 520 }}>
          <p className="wiz-card-subtitle">No questionnaire available for this system.</p>
          <div className="wiz-nav">
            <div className="wiz-nav-left" />
            <div className="wiz-nav-right">
              <button className="wiz-btn-reveal" type="button" onClick={goToReview}>Review Character</button>
            </div>
          </div>
        </div>
      )
    }

    const question      = questions[questionIndex]
    const totalQuestions = questions.length
    const progressPct  = Math.round(((questionIndex + 1) / totalQuestions) * 100)
    const isLast       = questionIndex === totalQuestions - 1
    const hasAnswer    = !!answers[question.id]

    const chapterNumerals = ['I','II','III','IV','V','VI','VII','VIII','IX','X',
                             'XI','XII','XIII','XIV','XV','XVI','XVII','XVIII','XIX','XX']

    return (
      <div className="wiz-card" style={{ maxWidth: 620 }}>
        {/* Progress */}
        <div className="wiz-progress-wrap">
          <div className="wiz-progress-meta">
            <span>Chapter {chapterNumerals[questionIndex] ?? questionIndex + 1}</span>
            <span>{questionIndex + 1} / {totalQuestions}</span>
          </div>
          <div className="wiz-progress-track">
            <div className="wiz-progress-fill" style={{ width: `${progressPct}%` }} />
          </div>
          <div className="wiz-chapter-dots">
            {questions.map((_, i) => (
              <div
                key={i}
                className={`wiz-chapter-dot${
                  i === questionIndex ? ' is-active' : i < questionIndex || answers[questions[i].id] ? ' is-done' : ''
                }`}
              />
            ))}
          </div>
        </div>

        {/* Question */}
        <div className="wiz-card-eyebrow">{question.id.replace(/_/g, ' ')}</div>
        <div className="wiz-q-text">{question.text}</div>

        {/* Options */}
        <div className="wiz-options">
          {question.choices.map((choice) => {
            const selected = answers[question.id] === choice.id
            return (
              <button
                key={choice.id}
                type="button"
                className={`wiz-option${selected ? ' is-selected' : ''}`}
                onClick={() => setAnswers((prev) => ({ ...prev, [question.id]: choice.id }))}
              >
                <div style={{ flex: 1 }}>
                  <div className="wiz-option-title">{choice.text}</div>
                  {choice.narrative && (
                    <div className="wiz-option-desc">{choice.narrative}</div>
                  )}
                  {selected && choice.skills.length > 0 && (
                    <div className="wiz-option-skills">
                      ⚔ Skills: {choice.skills.join(', ')}
                    </div>
                  )}
                </div>
              </button>
            )
          })}
        </div>

        {/* Nav */}
        <div className="wiz-nav">
          <div className="wiz-nav-left">
            <button
              className="wiz-btn-back"
              type="button"
              onClick={() => {
                if (questionIndex === 0) setStep('mode')
                else setQuestionIndex((i) => i - 1)
              }}
            >
              ← Back
            </button>
          </div>
          <div className="wiz-nav-right">
            {isLast ? (
              <button
                className={hasAnswer ? 'wiz-btn-reveal' : 'wiz-btn-next'}
                type="button"
                disabled={!hasAnswer}
                onClick={goToReview}
              >
                ✦ Review Character ✦
              </button>
            ) : (
              <button
                className="wiz-btn-next"
                type="button"
                disabled={!hasAnswer}
                onClick={() => setQuestionIndex((i) => i + 1)}
              >
                Continue →
              </button>
            )}
          </div>
        </div>
      </div>
    )
  }

  // ---- Manual ----
  function renderManualStep() {
    return (
      <div className="wiz-card" style={{ maxWidth: 560 }}>
        <div className="wiz-card-eyebrow">Step V — Chronicle</div>
        <h2 className="wiz-card-title">Write Your Chronicle</h2>
        <p className="wiz-card-subtitle">
          Fill in the details of your character's history, training, and tongue.
        </p>
        <div className="wiz-divider"><div className="wiz-divider-line"/><div className="wiz-divider-gem"/><div className="wiz-divider-line"/></div>

        <div className="wiz-field">
          <span className="wiz-label">Skill Proficiencies</span>
          <input
            className="wiz-input"
            placeholder="e.g. Stealth, Persuasion, Athletics"
            value={manualSkills}
            onChange={(e) => setManualSkills(e.target.value)}
          />
          <span className="wiz-label-hint">Comma-separated list of skills.</span>
        </div>

        <div className="wiz-field">
          <span className="wiz-label">Background</span>
          <input
            className="wiz-input"
            placeholder="e.g. Soldier, Sage, Folk Hero"
            value={manualBackground}
            onChange={(e) => setManualBackground(e.target.value)}
          />
        </div>

        <div className="wiz-field">
          <span className="wiz-label">Languages</span>
          <input
            className="wiz-input"
            placeholder="e.g. Common, Elvish"
            value={manualLanguages}
            onChange={(e) => setManualLanguages(e.target.value)}
          />
        </div>

        <div className="wiz-field">
          <span className="wiz-label">Starting Equipment</span>
          <input
            className="wiz-input"
            placeholder="e.g. Longsword, chain mail, explorer's pack"
            value={manualEquipment}
            onChange={(e) => setManualEquipment(e.target.value)}
          />
        </div>

        <div className="wiz-field">
          <span className="wiz-label">Backstory</span>
          <textarea
            className="wiz-textarea"
            placeholder="Describe your character's history, motivations, and personality…"
            value={manualBackstory}
            onChange={(e) => setManualBackstory(e.target.value)}
            rows={5}
          />
        </div>

        <div className="wiz-nav">
          <div className="wiz-nav-left">
            <button className="wiz-btn-back" type="button" onClick={() => setStep('mode')}>← Back</button>
          </div>
          <div className="wiz-nav-right">
            <button className="wiz-btn-reveal" type="button" onClick={goToReview}>
              ✦ Review Character ✦
            </button>
          </div>
        </div>
      </div>
    )
  }

  // ---- Review ----
  function renderReviewStep() {
    const abilityScores = systemConfig?.ability_scores ?? []
    return (
      <div className="wiz-card" style={{ maxWidth: 640 }}>
        <div className="wiz-card-eyebrow">Step VI — Seal of Fate</div>
        <h2 className="wiz-card-title">Review Your Character</h2>
        <p className="wiz-card-subtitle">
          All fields are editable. Make any final adjustments before your fate is sealed.
        </p>
        <div className="wiz-divider"><div className="wiz-divider-line"/><div className="wiz-divider-gem"/><div className="wiz-divider-line"/></div>

        {saveError && <div className="wiz-error">{saveError}</div>}

        {/* Identity */}
        <div className="wiz-review-section wiz-gap-md">
          <div className="wiz-review-section-title">✦ Identity</div>
          <div className="wiz-review-2col">
            <div className="wiz-field">
              <span className="wiz-label">Name</span>
              <input className="wiz-input" value={reviewName} onChange={(e) => setReviewName(e.target.value)} />
            </div>
            <div className="wiz-field">
              <span className="wiz-label">Class</span>
              <input className="wiz-input" value={reviewClass} onChange={(e) => setReviewClass(e.target.value)} />
            </div>
            <div className="wiz-field">
              <span className="wiz-label">Level</span>
              <input
                className="wiz-input wiz-input-sm"
                type="number" min={1} max={20}
                value={reviewLevel}
                onChange={(e) => setReviewLevel(Math.max(1, Math.min(20, Number(e.target.value) || 1)))}
              />
            </div>
            <div className="wiz-field">
              <span className="wiz-label">System</span>
              <input className="wiz-input" value={gameSystem} readOnly />
            </div>
          </div>
        </div>

        {/* Ability Scores */}
        {abilityScores.length > 0 && (
          <div className="wiz-review-section wiz-gap-md">
            <div className="wiz-review-section-title">✦ Ability Scores</div>
            <div className="wiz-ability-chips">
              {abilityScores.map((score) => {
                const val = finalAbilityScores[score.key]
                return (
                  <div key={score.key} className="wiz-ability-chip">
                    <div className="wiz-ability-chip-key">{score.label.substring(0, 3).toUpperCase()}</div>
                    <div className={`wiz-ability-chip-val${val == null ? ' is-empty' : ''}`}>
                      {val != null ? val : '—'}
                    </div>
                  </div>
                )
              })}
            </div>
            {Object.values(finalAbilityScores).length < abilityScores.length && (
              <p className="wiz-hint">⚠ Some ability scores are unassigned — you can go back to assign them.</p>
            )}
          </div>
        )}

        {/* Traits */}
        <div className="wiz-review-section wiz-gap-md">
          <div className="wiz-review-section-title">✦ Traits &amp; Proficiencies</div>
          <div className="wiz-field">
            <span className="wiz-label">Skill Proficiencies</span>
            <input className="wiz-input" value={reviewSkills} onChange={(e) => setReviewSkills(e.target.value)} placeholder="e.g. Stealth, Persuasion" />
          </div>
          <div className="wiz-field">
            <span className="wiz-label">Background</span>
            <input className="wiz-input" value={reviewBackground} onChange={(e) => setReviewBackground(e.target.value)} placeholder="e.g. Soldier" />
          </div>
          <div className="wiz-field">
            <span className="wiz-label">Languages</span>
            <input className="wiz-input" value={reviewLanguages} onChange={(e) => setReviewLanguages(e.target.value)} placeholder="e.g. Common, Elvish" />
          </div>
          <div className="wiz-field">
            <span className="wiz-label">Starting Equipment</span>
            <input className="wiz-input" value={reviewEquipment} onChange={(e) => setReviewEquipment(e.target.value)} placeholder="e.g. Longsword, chain mail" />
          </div>
        </div>

        {/* Backstory */}
        <div className="wiz-review-section wiz-gap-md">
          <div className="wiz-review-section-title">✦ Backstory</div>
          <div className="wiz-field">
            <textarea
              className="wiz-textarea"
              value={reviewBackstory}
              onChange={(e) => setReviewBackstory(e.target.value)}
              placeholder="Your character's history and motivations…"
              rows={5}
            />
          </div>
        </div>

        <div className="wiz-nav">
          <div className="wiz-nav-left">
            <button
              className="wiz-btn-back"
              type="button"
              onClick={() => setStep(creationMode === 'helper' ? 'questionnaire' : 'manual')}
            >
              ← Back
            </button>
          </div>
          <div className="wiz-nav-right">
            <button
              className="wiz-btn-secondary"
              type="button"
              disabled={saving || !reviewName.trim()}
              onClick={() => save(false)}
            >
              {saving ? 'Saving…' : 'Confirm'}
            </button>
            <button
              className="wiz-btn-reveal"
              type="button"
              disabled={saving || !reviewName.trim()}
              onClick={() => save(true)}
            >
              {saving ? 'Saving…' : '✦ Confirm & Play ✦'}
            </button>
          </div>
        </div>
      </div>
    )
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <section className="dashboard-panel stack wiz-root">
      <PageHeader
        title="Create Character"
        subtitle={`Guided character creation${gameSystem ? ` — ${gameSystem}` : ''}`}
        actions={
          <button className="btn btn-quiet" type="button" onClick={onDone}>
            Cancel
          </button>
        }
      />
      {renderStepIndicator()}
      {step === 'system'        && renderSystemStep()}
      {step === 'basics'        && renderBasicsStep()}
      {step === 'abilities'     && renderAbilitiesStep()}
      {step === 'mode'          && renderModeStep()}
      {step === 'questionnaire' && renderQuestionnaireStep()}
      {step === 'manual'        && renderManualStep()}
      {step === 'review'        && renderReviewStep()}
    </section>
  )
}
