import React, { useCallback, useEffect, useMemo, useState } from 'react'

import { apiFetch } from '../../api'
import PageHeader from '../ui/PageHeader'

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
  // Step renderers
  // ---------------------------------------------------------------------------

  function renderStepIndicator() {
    const steps: { key: WizardStep; label: string }[] = [
      { key: 'system', label: 'System' },
      { key: 'basics', label: 'Basics' },
      { key: 'abilities', label: 'Abilities' },
      { key: 'mode', label: 'Mode' },
      { key: creationMode === 'helper' ? 'questionnaire' : 'manual', label: creationMode === 'helper' ? 'Questions' : 'Details' },
      { key: 'review', label: 'Review' },
    ]
    return (
      <div style={{ display: 'flex', gap: 8, marginBottom: 24, flexWrap: 'wrap' }}>
        {steps.map(({ key, label }, i) => {
          const isActive = step === key
          const isDone =
            steps.findIndex((s) => s.key === step) > i
          return (
            <div
              key={key}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                fontSize: 13,
                color: isActive ? 'var(--color-accent, #E09A4F)' : isDone ? 'var(--color-text-muted, #8a7963)' : 'var(--color-text-muted, #8a7963)',
                fontWeight: isActive ? 700 : 400,
              }}
            >
              <span
                style={{
                  width: 22,
                  height: 22,
                  borderRadius: '50%',
                  background: isActive
                    ? 'var(--color-accent, #E09A4F)'
                    : isDone
                    ? 'var(--color-accent-faint, #5a4a35)'
                    : 'var(--color-surface-3, #2e2822)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: isActive ? '#fff' : isDone ? 'var(--color-accent, #E09A4F)' : 'var(--color-text-muted, #8a7963)',
                  fontSize: 11,
                  fontWeight: 700,
                  flexShrink: 0,
                }}
              >
                {isDone ? '✓' : i + 1}
              </span>
              {label}
              {i < steps.length - 1 && (
                <span style={{ color: 'var(--color-text-muted, #8a7963)', marginLeft: 4 }}>›</span>
              )}
            </div>
          )
        })}
      </div>
    )
  }

  function renderSystemStep() {
    return (
      <div className="card card-pad stack" style={{ maxWidth: 640 }}>
        <div style={{ fontWeight: 700, fontSize: 16 }}>Choose a game system</div>
        <div className="muted" style={{ fontSize: 13 }}>
          Select the tabletop RPG system this character is built for. The wizard will adapt
          classes, ability scores, and questions to match your choice.
        </div>
        {configError && <div className="muted" style={{ color: 'var(--color-error, #e05050)' }}>{configError}</div>}
        <div style={{ display: 'grid', gap: 8 }}>
          {systems.map((sys) => (
            <button
              key={sys.name}
              type="button"
              className={`card card-pad${gameSystem === sys.name ? ' card-selected' : ''}`}
              style={{
                textAlign: 'left',
                cursor: 'pointer',
                border: gameSystem === sys.name
                  ? '2px solid var(--color-accent, #E09A4F)'
                  : '2px solid transparent',
                background: gameSystem === sys.name
                  ? 'var(--color-surface-2, #2a2420)'
                  : undefined,
              }}
              onClick={() => setGameSystem(sys.name)}
            >
              <div style={{ fontWeight: 600 }}>{sys.name}</div>
              <div className="muted" style={{ fontSize: 12 }}>{sys.publisher}</div>
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
          <button className="btn btn-quiet" type="button" onClick={onDone}>
            Cancel
          </button>
          <button
            className="btn"
            type="button"
            disabled={!gameSystem}
            onClick={() => {
              if (systemConfig) initAbilities(systemConfig)
              setStep('basics')
            }}
          >
            Next
          </button>
        </div>
      </div>
    )
  }

  function renderBasicsStep() {
    const classes = systemConfig?.classes ?? []
    return (
      <div className="card card-pad stack" style={{ maxWidth: 480 }}>
        <div style={{ fontWeight: 700, fontSize: 16 }}>Character basics</div>
        <div className="muted" style={{ fontSize: 13 }}>
          Give your character a name, pick a class, and choose a starting level.
        </div>
        <label style={{ display: 'grid', gap: 4 }}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>Name *</span>
          <input
            className="input"
            placeholder="Enter character name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label style={{ display: 'grid', gap: 4 }}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>Class</span>
          {classes.length > 0 ? (
            <select
              className="input"
              value={characterClass}
              onChange={(e) => setCharacterClass(e.target.value)}
            >
              <option value="">— Select class —</option>
              {classes.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          ) : (
            <input
              className="input"
              placeholder="Class (optional)"
              value={characterClass}
              onChange={(e) => setCharacterClass(e.target.value)}
            />
          )}
        </label>
        <label style={{ display: 'grid', gap: 4 }}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>Level</span>
          <input
            className="input"
            type="number"
            min={1}
            max={20}
            value={level}
            onChange={(e) => setLevel(Math.max(1, Math.min(20, Number(e.target.value) || 1)))}
            style={{ maxWidth: 100 }}
          />
        </label>
        <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
          <button className="btn btn-quiet" type="button" onClick={() => setStep('system')}>
            Back
          </button>
          <button
            className="btn"
            type="button"
            disabled={!name.trim()}
            onClick={() => setStep('abilities')}
          >
            Next
          </button>
        </div>
      </div>
    )
  }

  function renderAbilitiesStep() {
    const config = systemConfig
    if (!config) return null
    const unassigned = config.standard_array.filter(
      (v) => !Object.values(arrayAssignments).includes(v),
    )

    return (
      <div className="card card-pad stack" style={{ maxWidth: 600 }}>
        <div style={{ fontWeight: 700, fontSize: 16 }}>Ability scores</div>
        <div className="muted" style={{ fontSize: 13 }}>
          Choose how to generate ability scores for your character.
        </div>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <button
            type="button"
            className={`btn${abilityMethod === 'standard-array' ? '' : ' btn-secondary'}`}
            onClick={() => setAbilityMethod('standard-array')}
          >
            Standard Array
          </button>
          {config.point_buy_budget > 0 && (
            <button
              type="button"
              className={`btn${abilityMethod === 'point-buy' ? '' : ' btn-secondary'}`}
              onClick={() => setAbilityMethod('point-buy')}
            >
              Point Buy
            </button>
          )}
        </div>

        {abilityMethod === 'standard-array' && (
          <div>
            <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
              Assign each value from the standard array [{config.standard_array.join(', ')}] to an ability score.
            </div>
            <div style={{ display: 'grid', gap: 8 }}>
              {config.ability_scores.map((score) => (
                <div key={score.key} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <span style={{ minWidth: 120, fontSize: 13, fontWeight: 600 }}>{score.label}</span>
                  <select
                    className="input"
                    style={{ maxWidth: 100 }}
                    value={arrayAssignments[score.key] ?? ''}
                    onChange={(e) => {
                      const newVal = e.target.value === '' ? null : Number(e.target.value)
                      setArrayAssignments((prev) => {
                        const next = { ...prev }
                        // De-assign other abilities that have this value
                        if (newVal != null) {
                          for (const k of Object.keys(next)) {
                            if (next[k] === newVal && k !== score.key) {
                              next[k] = null
                            }
                          }
                        }
                        next[score.key] = newVal
                        return next
                      })
                    }}
                  >
                    <option value="">— pick —</option>
                    {config.standard_array.map((v) => {
                      const taken =
                        Object.entries(arrayAssignments).some(
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
                    <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--color-accent, #E09A4F)' }}>
                      {arrayAssignments[score.key]}
                    </span>
                  )}
                </div>
              ))}
            </div>
            {unassigned.length > 0 && (
              <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
                Unassigned values: [{unassigned.join(', ')}]
              </div>
            )}
          </div>
        )}

        {abilityMethod === 'point-buy' && (
          <div>
            <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
              Spend {config.point_buy_budget} points. Each ability starts at {config.point_buy_min}.
              Budget remaining: <strong>{pointBuyRemaining}</strong>
            </div>
            <div style={{ display: 'grid', gap: 8 }}>
              {config.ability_scores.map((score) => {
                const val = pointBuyValues[score.key] ?? config.point_buy_min
                const canIncrease =
                  val < config.point_buy_max && pointBuyRemaining > 0
                const canDecrease = val > config.point_buy_min
                return (
                  <div key={score.key} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <span style={{ minWidth: 120, fontSize: 13, fontWeight: 600 }}>
                      {score.label}
                    </span>
                    <button
                      type="button"
                      className="btn btn-quiet"
                      style={{ padding: '2px 8px', minWidth: 28 }}
                      disabled={!canDecrease}
                      onClick={() =>
                        setPointBuyValues((prev) => ({ ...prev, [score.key]: val - 1 }))
                      }
                    >
                      −
                    </button>
                    <span style={{ minWidth: 28, textAlign: 'center', fontWeight: 700 }}>{val}</span>
                    <button
                      type="button"
                      className="btn btn-quiet"
                      style={{ padding: '2px 8px', minWidth: 28 }}
                      disabled={!canIncrease}
                      onClick={() =>
                        setPointBuyValues((prev) => ({ ...prev, [score.key]: val + 1 }))
                      }
                    >
                      +
                    </button>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
          <button className="btn btn-quiet" type="button" onClick={() => setStep('basics')}>
            Back
          </button>
          <button
            className="btn"
            type="button"
            onClick={() => setStep('mode')}
          >
            Next
          </button>
        </div>
      </div>
    )
  }

  function renderModeStep() {
    return (
      <div className="card card-pad stack" style={{ maxWidth: 560 }}>
        <div style={{ fontWeight: 700, fontSize: 16 }}>Choose your creation style</div>
        <div className="muted" style={{ fontSize: 13 }}>
          How would you like to flesh out your character's background, skills, and story?
        </div>
        <div style={{ display: 'grid', gap: 12 }}>
          <button
            type="button"
            className="card card-pad"
            style={{
              textAlign: 'left',
              cursor: 'pointer',
              border: creationMode === 'helper'
                ? '2px solid var(--color-accent, #E09A4F)'
                : '2px solid transparent',
            }}
            onClick={() => setCreationMode('helper')}
          >
            <div style={{ fontWeight: 700 }}>🎲 Helper Mode — Guided Questionnaire</div>
            <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
              Answer a short series of scenario questions. Your choices will automatically
              determine skill proficiencies, background, and weave a backstory for your character.
            </div>
          </button>
          <button
            type="button"
            className="card card-pad"
            style={{
              textAlign: 'left',
              cursor: 'pointer',
              border: creationMode === 'manual'
                ? '2px solid var(--color-accent, #E09A4F)'
                : '2px solid transparent',
            }}
            onClick={() => setCreationMode('manual')}
          >
            <div style={{ fontWeight: 700 }}>✏️ Manual Mode — Full Control</div>
            <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
              Enter all character details by hand. Choose exactly which skills, languages, and
              background traits define your character.
            </div>
          </button>
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
          <button className="btn btn-quiet" type="button" onClick={() => setStep('abilities')}>
            Back
          </button>
          <button
            className="btn"
            type="button"
            onClick={() => {
              setAnswers({})
              setQuestionIndex(0)
              setStep(creationMode === 'helper' ? 'questionnaire' : 'manual')
            }}
          >
            Next
          </button>
        </div>
      </div>
    )
  }

  function renderQuestionnaireStep() {
    const questions = systemConfig?.questions ?? []
    if (questions.length === 0) {
      return (
        <div className="card card-pad stack" style={{ maxWidth: 560 }}>
          <div className="muted">No questionnaire available for this system.</div>
          <button className="btn" type="button" onClick={goToReview}>Continue to Review</button>
        </div>
      )
    }
    const question = questions[questionIndex]
    const totalQuestions = questions.length
    const progress = Math.round(((questionIndex) / totalQuestions) * 100)

    return (
      <div className="card card-pad stack" style={{ maxWidth: 600 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ fontWeight: 700, fontSize: 16 }}>Question {questionIndex + 1} of {totalQuestions}</div>
          <div className="muted" style={{ fontSize: 12 }}>{progress}% complete</div>
        </div>
        <div
          style={{
            height: 4,
            background: 'var(--color-surface-3, #2e2822)',
            borderRadius: 2,
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              height: '100%',
              width: `${progress}%`,
              background: 'var(--color-accent, #E09A4F)',
              transition: 'width 0.3s ease',
            }}
          />
        </div>
        <div style={{ fontSize: 15, fontWeight: 600, lineHeight: 1.5 }}>{question.text}</div>
        <div style={{ display: 'grid', gap: 10 }}>
          {question.choices.map((choice) => {
            const selected = answers[question.id] === choice.id
            return (
              <button
                key={choice.id}
                type="button"
                className="card card-pad"
                style={{
                  textAlign: 'left',
                  cursor: 'pointer',
                  border: selected
                    ? '2px solid var(--color-accent, #E09A4F)'
                    : '2px solid transparent',
                  background: selected ? 'var(--color-surface-2, #2a2420)' : undefined,
                }}
                onClick={() =>
                  setAnswers((prev) => ({ ...prev, [question.id]: choice.id }))
                }
              >
                <div style={{ fontWeight: selected ? 700 : 400 }}>{choice.text}</div>
                {selected && (
                  <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                    Skills: {choice.skills.join(', ')}
                  </div>
                )}
              </button>
            )
          })}
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
          <button
            className="btn btn-quiet"
            type="button"
            onClick={() => {
              if (questionIndex === 0) {
                setStep('mode')
              } else {
                setQuestionIndex((i) => i - 1)
              }
            }}
          >
            Back
          </button>
          {questionIndex < totalQuestions - 1 ? (
            <button
              className="btn"
              type="button"
              disabled={!answers[question.id]}
              onClick={() => setQuestionIndex((i) => i + 1)}
            >
              Next Question
            </button>
          ) : (
            <button
              className="btn"
              type="button"
              disabled={!answers[question.id]}
              onClick={goToReview}
            >
              Review Character
            </button>
          )}
        </div>
      </div>
    )
  }

  function renderManualStep() {
    return (
      <div className="card card-pad stack" style={{ maxWidth: 560 }}>
        <div style={{ fontWeight: 700, fontSize: 16 }}>Character details</div>
        <div className="muted" style={{ fontSize: 13 }}>
          Fill in your character's background, proficiencies, and story.
        </div>
        <label style={{ display: 'grid', gap: 4 }}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>Skill Proficiencies</span>
          <input
            className="input"
            placeholder="e.g. Stealth, Persuasion, Athletics"
            value={manualSkills}
            onChange={(e) => setManualSkills(e.target.value)}
          />
          <span className="muted" style={{ fontSize: 11 }}>Comma-separated list of skills.</span>
        </label>
        <label style={{ display: 'grid', gap: 4 }}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>Background</span>
          <input
            className="input"
            placeholder="e.g. Soldier, Sage, Folk Hero"
            value={manualBackground}
            onChange={(e) => setManualBackground(e.target.value)}
          />
        </label>
        <label style={{ display: 'grid', gap: 4 }}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>Languages</span>
          <input
            className="input"
            placeholder="e.g. Common, Elvish"
            value={manualLanguages}
            onChange={(e) => setManualLanguages(e.target.value)}
          />
        </label>
        <label style={{ display: 'grid', gap: 4 }}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>Starting Equipment</span>
          <input
            className="input"
            placeholder="e.g. Longsword, chain mail, explorer's pack"
            value={manualEquipment}
            onChange={(e) => setManualEquipment(e.target.value)}
          />
        </label>
        <label style={{ display: 'grid', gap: 4 }}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>Backstory</span>
          <textarea
            className="input"
            placeholder="Describe your character's history, motivations, and personality…"
            value={manualBackstory}
            onChange={(e) => setManualBackstory(e.target.value)}
            rows={4}
            style={{ resize: 'vertical' }}
          />
        </label>
        <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
          <button className="btn btn-quiet" type="button" onClick={() => setStep('mode')}>
            Back
          </button>
          <button className="btn" type="button" onClick={goToReview}>
            Review Character
          </button>
        </div>
      </div>
    )
  }

  function renderReviewStep() {
    const abilityScores = systemConfig?.ability_scores ?? []
    return (
      <div className="card card-pad stack" style={{ maxWidth: 640 }}>
        <div style={{ fontWeight: 700, fontSize: 16 }}>Review your character</div>
        <div className="muted" style={{ fontSize: 13 }}>
          Make any final adjustments before confirming. All fields are editable.
        </div>

        {saveError && (
          <div style={{ color: 'var(--color-error, #e05050)', fontSize: 13 }}>{saveError}</div>
        )}

        <div style={{ display: 'grid', gap: 16 }}>
          {/* Identity */}
          <div className="card card-pad stack" style={{ gap: 8 }}>
            <div style={{ fontWeight: 600, fontSize: 14, borderBottom: '1px solid var(--color-border, #3a3025)', paddingBottom: 6 }}>
              Identity
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <label style={{ display: 'grid', gap: 4 }}>
                <span style={{ fontSize: 12, fontWeight: 600 }}>Name</span>
                <input
                  className="input"
                  value={reviewName}
                  onChange={(e) => setReviewName(e.target.value)}
                />
              </label>
              <label style={{ display: 'grid', gap: 4 }}>
                <span style={{ fontSize: 12, fontWeight: 600 }}>Class</span>
                <input
                  className="input"
                  value={reviewClass}
                  onChange={(e) => setReviewClass(e.target.value)}
                />
              </label>
              <label style={{ display: 'grid', gap: 4 }}>
                <span style={{ fontSize: 12, fontWeight: 600 }}>Level</span>
                <input
                  className="input"
                  type="number"
                  min={1}
                  max={20}
                  value={reviewLevel}
                  onChange={(e) =>
                    setReviewLevel(Math.max(1, Math.min(20, Number(e.target.value) || 1)))
                  }
                  style={{ maxWidth: 80 }}
                />
              </label>
              <label style={{ display: 'grid', gap: 4 }}>
                <span style={{ fontSize: 12, fontWeight: 600 }}>System</span>
                <input className="input" value={gameSystem} readOnly />
              </label>
            </div>
          </div>

          {/* Ability Scores */}
          {abilityScores.length > 0 && (
            <div className="card card-pad stack" style={{ gap: 8 }}>
              <div style={{ fontWeight: 600, fontSize: 14, borderBottom: '1px solid var(--color-border, #3a3025)', paddingBottom: 6 }}>
                Ability Scores
              </div>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(110px, 1fr))',
                  gap: 8,
                }}
              >
                {abilityScores.map((score) => {
                  const val = finalAbilityScores[score.key]
                  return (
                    <div
                      key={score.key}
                      style={{
                        textAlign: 'center',
                        padding: '8px 4px',
                        background: 'var(--color-surface-3, #2e2822)',
                        borderRadius: 6,
                      }}
                    >
                      <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--color-text-muted, #8a7963)' }}>
                        {score.label.substring(0, 3).toUpperCase()}
                      </div>
                      <div style={{ fontSize: 20, fontWeight: 700, color: val != null ? 'var(--color-accent, #E09A4F)' : 'var(--color-text-muted, #8a7963)' }}>
                        {val != null ? val : '—'}
                      </div>
                    </div>
                  )
                })}
              </div>
              {Object.values(finalAbilityScores).length < abilityScores.length && (
                <div className="muted" style={{ fontSize: 12 }}>
                  ⚠ Some ability scores are unassigned. You can go back to assign them or continue without.
                </div>
              )}
            </div>
          )}

          {/* Character traits */}
          <div className="card card-pad stack" style={{ gap: 8 }}>
            <div style={{ fontWeight: 600, fontSize: 14, borderBottom: '1px solid var(--color-border, #3a3025)', paddingBottom: 6 }}>
              Traits &amp; Proficiencies
            </div>
            <label style={{ display: 'grid', gap: 4 }}>
              <span style={{ fontSize: 12, fontWeight: 600 }}>Skill Proficiencies</span>
              <input
                className="input"
                value={reviewSkills}
                onChange={(e) => setReviewSkills(e.target.value)}
                placeholder="e.g. Stealth, Persuasion"
              />
            </label>
            <label style={{ display: 'grid', gap: 4 }}>
              <span style={{ fontSize: 12, fontWeight: 600 }}>Background</span>
              <input
                className="input"
                value={reviewBackground}
                onChange={(e) => setReviewBackground(e.target.value)}
                placeholder="e.g. Soldier"
              />
            </label>
            <label style={{ display: 'grid', gap: 4 }}>
              <span style={{ fontSize: 12, fontWeight: 600 }}>Languages</span>
              <input
                className="input"
                value={reviewLanguages}
                onChange={(e) => setReviewLanguages(e.target.value)}
                placeholder="e.g. Common, Elvish"
              />
            </label>
            <label style={{ display: 'grid', gap: 4 }}>
              <span style={{ fontSize: 12, fontWeight: 600 }}>Starting Equipment</span>
              <input
                className="input"
                value={reviewEquipment}
                onChange={(e) => setReviewEquipment(e.target.value)}
                placeholder="e.g. Longsword, chain mail"
              />
            </label>
          </div>

          {/* Backstory */}
          <div className="card card-pad stack" style={{ gap: 8 }}>
            <div style={{ fontWeight: 600, fontSize: 14, borderBottom: '1px solid var(--color-border, #3a3025)', paddingBottom: 6 }}>
              Backstory
            </div>
            <label style={{ display: 'grid', gap: 4 }}>
              <span style={{ fontSize: 12, fontWeight: 600 }}>Character backstory</span>
              <textarea
                className="input"
                value={reviewBackstory}
                onChange={(e) => setReviewBackstory(e.target.value)}
                placeholder="Your character's history and motivations…"
                rows={4}
                style={{ resize: 'vertical' }}
              />
            </label>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
          <button
            className="btn btn-quiet"
            type="button"
            onClick={() =>
              setStep(creationMode === 'helper' ? 'questionnaire' : 'manual')
            }
          >
            Back
          </button>
          <button
            className="btn btn-secondary"
            type="button"
            disabled={saving || !reviewName.trim()}
            onClick={() => save(false)}
          >
            {saving ? 'Saving…' : 'Confirm'}
          </button>
          <button
            className="btn"
            type="button"
            disabled={saving || !reviewName.trim()}
            onClick={() => save(true)}
          >
            {saving ? 'Saving…' : 'Confirm &amp; Play'}
          </button>
        </div>
      </div>
    )
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <section className="dashboard-panel stack">
      <PageHeader
        title="Create Character"
        subtitle={`Guided character creation wizard${gameSystem ? ` — ${gameSystem}` : ''}`}
        actions={
          <button className="btn btn-quiet" type="button" onClick={onDone}>
            Cancel
          </button>
        }
      />
      {renderStepIndicator()}
      {step === 'system' && renderSystemStep()}
      {step === 'basics' && renderBasicsStep()}
      {step === 'abilities' && renderAbilitiesStep()}
      {step === 'mode' && renderModeStep()}
      {step === 'questionnaire' && renderQuestionnaireStep()}
      {step === 'manual' && renderManualStep()}
      {step === 'review' && renderReviewStep()}
    </section>
  )
}
