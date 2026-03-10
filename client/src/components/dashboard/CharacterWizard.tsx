/**
 * CharacterWizard.tsx
 *
 * System-specific character creation wizard. Guides the user through:
 *   1. System selection
 *   2. Ancestry / Race / Species (if applicable)
 *   3. Class / Occupation / Career
 *   4. Background quiz  (narrative questions → suggested background)
 *   5. Personality quick-picks
 *   6. Skill proficiency selection
 *   7. Name + Level
 *   8. Review & Create
 *
 * Design goals:
 *   - Minimize typing (name is the only text input)
 *   - All other steps are click-to-select visual cards
 *   - Each step fits one screen without scrolling
 *   - Running preview sidebar shows current choices
 */

import React, { useState } from 'react'
import { apiFetch } from '../../api'
import PageHeader from '../ui/PageHeader'
import {
  WIZARD_SYSTEMS,
  getSystem,
  scoreBackgroundQuiz,
  DND_VIRTUES,
  DND_FLAWS,
  DND_BONDS,
  SIMPLE_TRAITS,
  type SystemId,
  type WizardSystem,
  type FeatOption,
} from '../../data/wizard-data'
import './wizard.css'

// ─────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────

type Step =
  | 'system'
  | 'ancestry'
  | 'class'
  | 'features'
  | 'ability-scores'
  | 'background-quiz'
  | 'personality'
  | 'skills'
  | 'feats'
  | 'languages'
  | 'name-level'
  | 'review'

type AbilityScores = {
  str: number | null
  dex: number | null
  con: number | null
  int: number | null
  wis: number | null
  cha: number | null
}

type CharacterDraft = {
  systemId: SystemId | null
  ancestryId: string | null
  classId: string | null
  /** quiz question id → selected option id */
  quizAnswers: Record<string, string>
  /** resolved background id */
  backgroundId: string | null
  /** personality selections */
  virtue: string | null
  flaw: string | null
  bond: string | null
  simpleTrait: string | null
  abilityScores: AbilityScores
  selectedLanguages: string[]
  selectedSkills: string[]
  /** feat IDs selected during creation */
  selectedFeatIds: string[]
  name: string
  level: number
}

const EMPTY_ABILITY_SCORES: AbilityScores = { str: null, dex: null, con: null, int: null, wis: null, cha: null }

const EMPTY_DRAFT: CharacterDraft = {
  systemId: null,
  ancestryId: null,
  classId: null,
  quizAnswers: {},
  backgroundId: null,
  virtue: null,
  flaw: null,
  bond: null,
  simpleTrait: null,
  abilityScores: { ...EMPTY_ABILITY_SCORES },
  selectedLanguages: [],
  selectedSkills: [],
  selectedFeatIds: [],
  name: '',
  level: 1,
}

// ─────────────────────────────────────────────
// Step ordering helper
// ─────────────────────────────────────────────

function buildStepList(system: WizardSystem | undefined): Step[] {
  const steps: Step[] = ['system']
  if (!system) return steps
  if (system.ancestryLabel && system.ancestries?.length) steps.push('ancestry')
  steps.push('class')
  // Show features step if any class or ancestry in this system has annotated features/traits
  const hasFeatureData =
    system.classes.some((c) => (c.level1Features?.length ?? 0) > 0) ||
    (system.ancestries?.some((a) => (a.traits?.length ?? 0) > 0) ?? false)
  if (hasFeatureData) steps.push('features')
  if (system.abilityScoreMethod) steps.push('ability-scores')
  if (system.backgroundQuiz.length > 0) steps.push('background-quiz')
  if (system.personalityFormat !== 'none') steps.push('personality')
  if (system.skills.length > 0) steps.push('skills')
  if (system.feats?.length) steps.push('feats')
  if (system.availableLanguages?.length && system.languageCount) steps.push('languages')
  steps.push('name-level')
  steps.push('review')
  return steps
}

// ─────────────────────────────────────────────
// Progress indicator
// ─────────────────────────────────────────────

const STEP_LABELS: Record<Step, string> = {
  system: 'System',
  ancestry: 'Ancestry',
  class: 'Class',
  features: 'Features',
  'ability-scores': 'Abilities',
  'background-quiz': 'Background',
  personality: 'Personality',
  skills: 'Skills',
  feats: 'Feats',
  languages: 'Languages',
  'name-level': 'Name',
  review: 'Review',
}

function WizardProgress({ steps, current }: { steps: Step[]; current: Step }) {
  const currentIdx = steps.indexOf(current)
  return (
    <div className="wizard-progress" style={{ overflowX: 'auto', paddingBottom: 2 }}>
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
// Preview sidebar
// ─────────────────────────────────────────────

function CharacterPreview({ draft, system }: { draft: CharacterDraft; system: WizardSystem | undefined }) {
  const ancestry = system?.ancestries?.find((a) => a.id === draft.ancestryId)
  const cls = system?.classes.find((c) => c.id === draft.classId)
  const background = system?.backgrounds.find((b) => b.id === draft.backgroundId)

  return (
    <div className="wizard-preview">
      <div className="wizard-preview-title">Character</div>
      {draft.name && (
        <div className="wizard-preview-row">
          <span className="wizard-preview-label">Name</span>
          <span className="wizard-preview-value">{draft.name}</span>
        </div>
      )}
      {system && (
        <div className="wizard-preview-row">
          <span className="wizard-preview-label">System</span>
          <span className="wizard-preview-value">{system.emoji} {system.name}</span>
        </div>
      )}
      {ancestry && (
        <div className="wizard-preview-row">
          <span className="wizard-preview-label">{system?.ancestryLabel ?? 'Race'}</span>
          <span className="wizard-preview-value">{ancestry.emoji} {ancestry.name}</span>
        </div>
      )}
      {cls && (
        <div className="wizard-preview-row">
          <span className="wizard-preview-label">{system?.classLabel ?? 'Class'}</span>
          <span className="wizard-preview-value">{cls.emoji} {cls.name}</span>
        </div>
      )}
      {background && (
        <div className="wizard-preview-row">
          <span className="wizard-preview-label">Background</span>
          <span className="wizard-preview-value">{background.name}</span>
        </div>
      )}
      {Object.values(draft.abilityScores).some((v) => v !== null) && (
        <div className="wizard-preview-row" style={{ flexDirection: 'column', gap: 4 }}>
          <span className="wizard-preview-label">Abilities</span>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '2px 6px', textAlign: 'center' }}>
            {(['str','dex','con','int','wis','cha'] as const).map((stat) => {
              const v = draft.abilityScores[stat]
              if (v === null) return null
              const mod = Math.floor((v - 10) / 2)
              return (
                <div key={stat} style={{ fontSize: 10 }}>
                  <div style={{ color: 'var(--muted-text)', textTransform: 'uppercase' }}>{stat}</div>
                  <div style={{ fontWeight: 700, fontSize: 12 }}>{v}</div>
                  <div style={{ color: 'var(--accent)', fontSize: 10 }}>{mod >= 0 ? `+${mod}` : mod}</div>
                </div>
              )
            })}
          </div>
        </div>
      )}
      {draft.selectedSkills.length > 0 && (
        <div className="wizard-preview-row" style={{ flexDirection: 'column', gap: 4 }}>
          <span className="wizard-preview-label">Skills</span>
          <span className="wizard-preview-value" style={{ textAlign: 'left', fontSize: 11, whiteSpace: 'normal' }}>
            {draft.selectedSkills.join(', ')}
          </span>
        </div>
      )}
      {draft.selectedLanguages.length > 0 && (
        <div className="wizard-preview-row" style={{ flexDirection: 'column', gap: 4 }}>
          <span className="wizard-preview-label">Languages</span>
          <span className="wizard-preview-value" style={{ textAlign: 'left', fontSize: 11, whiteSpace: 'normal' }}>
            Common{draft.selectedLanguages.length > 0 ? `, ${draft.selectedLanguages.join(', ')}` : ''}
          </span>
        </div>
      )}
      {system?.levelRange && (
        <div className="wizard-preview-row">
          <span className="wizard-preview-label">Level</span>
          <span className="wizard-preview-value">{draft.level}</span>
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────
// Individual step components
// ─────────────────────────────────────────────

function StepSystem({ draft, onSelect }: { draft: CharacterDraft; onSelect: (id: SystemId) => void }) {
  return (
    <div className="wizard-body">
      <div>
        <div className="wizard-step-heading">Choose your game system</div>
        <div className="wizard-step-sub">Which ruleset are you playing?</div>
      </div>
      <div className="wizard-option-grid wizard-option-grid--wide">
        {WIZARD_SYSTEMS.map((sys) => (
          <button
            key={sys.id}
            type="button"
            className={`wizard-option-card${draft.systemId === sys.id ? ' is-selected' : ''}`}
            onClick={() => onSelect(sys.id)}
          >
            <span className="wizard-option-emoji">{sys.emoji}</span>
            <span className="wizard-option-name">{sys.name}</span>
            <span className="wizard-option-desc">{sys.genre}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

function StepAncestry({ draft, system, onSelect }: { draft: CharacterDraft; system: WizardSystem; onSelect: (id: string) => void }) {
  return (
    <div className="wizard-body">
      <div>
        <div className="wizard-step-heading">{system.ancestryLabel}</div>
        <div className="wizard-step-sub">What is your character's heritage?</div>
      </div>
      <div className="wizard-option-grid">
        {(system.ancestries ?? []).map((a) => (
          <button
            key={a.id}
            type="button"
            className={`wizard-option-card${draft.ancestryId === a.id ? ' is-selected' : ''}`}
            onClick={() => onSelect(a.id)}
          >
            <span className="wizard-option-emoji">{a.emoji}</span>
            <span className="wizard-option-name">{a.name}</span>
            <span className="wizard-option-desc">{a.description}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

function StepClass({ draft, system, onSelect }: { draft: CharacterDraft; system: WizardSystem; onSelect: (id: string) => void }) {
  return (
    <div className="wizard-body">
      <div>
        <div className="wizard-step-heading">{system.classLabel}</div>
        <div className="wizard-step-sub">What role does your character fill?</div>
      </div>
      <div className="wizard-option-grid">
        {system.classes.map((cls) => (
          <button
            key={cls.id}
            type="button"
            className={`wizard-option-card${draft.classId === cls.id ? ' is-selected' : ''}`}
            onClick={() => onSelect(cls.id)}
          >
            <span className="wizard-option-emoji">{cls.emoji}</span>
            <span className="wizard-option-name">{cls.name}</span>
            <span className="wizard-option-desc">{cls.description}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

function StepBackgroundQuiz({
  draft,
  system,
  quizIndex,
  onAnswer,
}: {
  draft: CharacterDraft
  system: WizardSystem
  quizIndex: number
  onAnswer: (qId: string, optionId: string) => void
}) {
  const question = system.backgroundQuiz[quizIndex]
  if (!question) return null

  const total = system.backgroundQuiz.length
  const currentAnswer = draft.quizAnswers[question.id]

  return (
    <div className="wizard-body">
      <div>
        <div className="wizard-step-heading">{system.backgroundLabel}</div>
        <div className="wizard-step-sub">
          Question {quizIndex + 1} of {total} — your answers will suggest a background
        </div>
      </div>
      <div className="wizard-scenario-card">
        <div className="wizard-scenario-prompt">{question.prompt}</div>
        <div className="wizard-answer-list">
          {question.options.map((opt) => (
            <button
              key={opt.id}
              type="button"
              className={`wizard-answer-btn${currentAnswer === opt.id ? ' is-selected' : ''}`}
              onClick={() => onAnswer(question.id, opt.id)}
            >
              <span style={{ fontSize: 18, flexShrink: 0 }}>
                {String.fromCharCode(65 + question.options.indexOf(opt))}.
              </span>
              <span>{opt.text}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function StepBackgroundPick({
  draft,
  system,
  onSelect,
}: {
  draft: CharacterDraft
  system: WizardSystem
  onSelect: (id: string) => void
}) {
  const ranked = scoreBackgroundQuiz(system, draft.quizAnswers)
  const suggested = ranked[0] ?? null

  return (
    <div className="wizard-body">
      <div>
        <div className="wizard-step-heading">Your Background</div>
        <div className="wizard-step-sub">
          Based on your answers{suggested ? ` — we suggest "${system.backgrounds.find(b => b.id === suggested)?.name ?? suggested}"` : ''}. Pick the one that fits best.
        </div>
      </div>
      <div className="wizard-option-grid wizard-option-grid--wide">
        {system.backgrounds.map((bg) => {
          const isSuggested = bg.id === ranked[0]
          const isSelected = draft.backgroundId === bg.id
          return (
            <button
              key={bg.id}
              type="button"
              className={`wizard-option-card${isSelected ? ' is-selected' : ''}`}
              onClick={() => onSelect(bg.id)}
              style={{ minHeight: 110 }}
            >
              {isSuggested && (
                <span style={{ fontSize: 10, color: 'var(--accent)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                  ★ Suggested
                </span>
              )}
              <span className="wizard-option-name">{bg.name}</span>
              <span className="wizard-option-desc">{bg.description}</span>
              {bg.suggestedSkills.length > 0 && (
                <span style={{ fontSize: 10, color: 'var(--muted-text)' }}>
                  Skills: {bg.suggestedSkills.join(', ')}
                </span>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}

function StepPersonality({
  draft,
  system,
  onUpdate,
}: {
  draft: CharacterDraft
  system: WizardSystem
  onUpdate: (key: 'virtue' | 'flaw' | 'bond' | 'simpleTrait', value: string) => void
}) {
  if (system.personalityFormat === 'dnd') {
    return (
      <div className="wizard-body">
        <div>
          <div className="wizard-step-heading">Personality</div>
          <div className="wizard-step-sub">Quick picks — give the AI a sense of who your character is.</div>
        </div>
        <div className="stack" style={{ gap: 12 }}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--muted-text)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
              Virtue — what drives your better nature
            </div>
            <div className="wizard-option-grid wizard-option-grid--tight">
              {DND_VIRTUES.map((v) => (
                <button
                  key={v.id}
                  type="button"
                  className={`wizard-option-card${draft.virtue === v.id ? ' is-selected' : ''}`}
                  onClick={() => onUpdate('virtue', v.id)}
                  style={{ minHeight: 50, padding: '10px 8px' }}
                >
                  <span className="wizard-option-name" style={{ fontSize: 12 }}>{v.label}</span>
                </button>
              ))}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--muted-text)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
              Flaw — what holds you back
            </div>
            <div className="wizard-option-grid wizard-option-grid--tight">
              {DND_FLAWS.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  className={`wizard-option-card${draft.flaw === f.id ? ' is-selected' : ''}`}
                  onClick={() => onUpdate('flaw', f.id)}
                  style={{ minHeight: 50, padding: '10px 8px' }}
                >
                  <span className="wizard-option-name" style={{ fontSize: 12 }}>{f.label}</span>
                </button>
              ))}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--muted-text)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
              Bond — what you hold most dear
            </div>
            <div className="wizard-option-grid wizard-option-grid--tight">
              {DND_BONDS.map((b) => (
                <button
                  key={b.id}
                  type="button"
                  className={`wizard-option-card${draft.bond === b.id ? ' is-selected' : ''}`}
                  onClick={() => onUpdate('bond', b.id)}
                  style={{ minHeight: 50, padding: '10px 8px' }}
                >
                  <span className="wizard-option-name" style={{ fontSize: 12 }}>{b.label}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    )
  }

  // simple format
  return (
    <div className="wizard-body">
      <div>
        <div className="wizard-step-heading">Personality</div>
        <div className="wizard-step-sub">How does your character approach the world?</div>
      </div>
      <div className="wizard-option-grid">
        {SIMPLE_TRAITS.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`wizard-option-card${draft.simpleTrait === t.id ? ' is-selected' : ''}`}
            onClick={() => onUpdate('simpleTrait', t.id)}
          >
            <span className="wizard-option-name">{t.label}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────
// Features step — read-only, shows what the character receives
// ─────────────────────────────────────────────

function StepFeatures({
  draft,
  system,
}: {
  draft: CharacterDraft
  system: WizardSystem
}) {
  const cls = system.classes.find((c) => c.id === draft.classId)
  const ancestry = system.ancestries?.find((a) => a.id === draft.ancestryId)
  const classFeatures = cls?.level1Features ?? []
  const ancestralTraits = ancestry?.traits ?? []
  const hasAny = classFeatures.length > 0 || ancestralTraits.length > 0

  return (
    <div className="wizard-body">
      <div>
        <div className="wizard-step-heading">Class & Ancestry Features</div>
        <div className="wizard-step-sub">
          Your character automatically gains these features at level 1.
          No action required — review them and continue.
        </div>
      </div>

      {!hasAny && (
        <div className="wizard-step-sub" style={{ marginTop: 12 }}>
          Select a class{system.ancestryLabel ? ' and ancestry' : ''} first to see features here.
        </div>
      )}

      {classFeatures.length > 0 && (
        <div className="wizard-feature-section">
          <div className="wizard-feature-section-label">
            {cls?.emoji && <span style={{ marginRight: 6 }}>{cls.emoji}</span>}
            {cls?.name} Features
            {cls?.hitDie && (
              <span className="wizard-feature-hit-die">d{cls.hitDie} hit die</span>
            )}
          </div>
          {cls?.saveProficiencies && cls.saveProficiencies.length > 0 && (
            <div className="wizard-feature-saves">
              Saving throw proficiencies: {cls.saveProficiencies.join(', ')}
            </div>
          )}
          <div className="wizard-feature-list">
            {classFeatures.map((f) => (
              <div key={f.name} className="wizard-feature-card">
                <div className="wizard-feature-name">
                  {f.name}
                  {f.level > 1 && <span className="wizard-feature-level-badge">lv.{f.level}</span>}
                </div>
                <div className="wizard-feature-summary">{f.summary}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {ancestralTraits.length > 0 && (
        <div className="wizard-feature-section">
          <div className="wizard-feature-section-label">
            {ancestry?.emoji && <span style={{ marginRight: 6 }}>{ancestry.emoji}</span>}
            {ancestry?.name} Traits
          </div>
          <div className="wizard-feature-list">
            {ancestralTraits.map((t) => (
              <div key={t.name} className="wizard-feature-card">
                <div className="wizard-feature-name">{t.name}</div>
                <div className="wizard-feature-summary">{t.summary}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────
// Feats step — optional feat selection
// ─────────────────────────────────────────────

const FEAT_TAGS: { id: string; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'combat', label: '⚔️ Combat' },
  { id: 'magic', label: '✨ Magic' },
  { id: 'utility', label: '🛠 Utility' },
  { id: 'social', label: '🗣 Social' },
]

function StepFeats({
  draft,
  system,
  onToggle,
}: {
  draft: CharacterDraft
  system: WizardSystem
  onToggle: (featId: string) => void
}) {
  const [activeTag, setActiveTag] = useState<string>('all')
  const feats: FeatOption[] = system.feats ?? []
  const max = system.featCountOnCreate ?? 1
  const selected = draft.selectedFeatIds
  const isMet = selected.length >= max

  const visible = activeTag === 'all'
    ? feats
    : feats.filter((f) => f.tags.includes(activeTag as any))

  return (
    <div className="wizard-body">
      <div>
        <div className="wizard-step-heading">Optional Feat</div>
        <div className="wizard-step-sub">
          Choose up to {max} feat{max !== 1 ? 's' : ''} for your character.
          Feats are optional — skip this step if you don&apos;t want one.
          Variant Human and Fighter receive feats at level 1 by default.
        </div>
      </div>

      {/* Tag filter */}
      <div className="wizard-feat-tag-bar">
        {FEAT_TAGS.map((tag) => (
          <button
            key={tag.id}
            type="button"
            className={`wizard-feat-tag-btn${activeTag === tag.id ? ' is-active' : ''}`}
            onClick={() => setActiveTag(tag.id)}
          >
            {tag.label}
          </button>
        ))}
      </div>

      <div className="wizard-feat-grid">
        {visible.map((feat) => {
          const isSelected = selected.includes(feat.id)
          const disabled = !isSelected && isMet
          return (
            <button
              key={feat.id}
              type="button"
              className={`wizard-feat-card${isSelected ? ' is-selected' : ''}${disabled ? ' is-disabled' : ''}`}
              onClick={() => !disabled && onToggle(feat.id)}
              disabled={disabled}
              title={disabled ? `Max ${max} feat${max !== 1 ? 's' : ''} selected` : undefined}
            >
              <div className="wizard-feat-name">{feat.name}</div>
              {feat.prerequisite && (
                <div className="wizard-feat-prereq">Requires: {feat.prerequisite}</div>
              )}
              <div className="wizard-feat-benefit">{feat.benefit}</div>
              <div className="wizard-feat-tags">
                {feat.tags.map((t) => (
                  <span key={t} className={`wizard-feat-tag wizard-feat-tag--${t}`}>{t}</span>
                ))}
              </div>
            </button>
          )
        })}
      </div>

      <div className={`wizard-selection-count${isMet ? ' wizard-selection-count--met' : ''}`}>
        {selected.length} / {max} selected
        {isMet ? ' — feat locked in!' : ' (optional — you can skip)'}
      </div>
    </div>
  )
}

function StepSkills({
  draft,
  system,
  onToggle,
}: {
  draft: CharacterDraft
  system: WizardSystem
  onToggle: (skillId: string) => void
}) {
  const background = system.backgrounds.find((b) => b.id === draft.backgroundId)
  const suggested = new Set(background?.suggestedSkills ?? [])
  const count = draft.selectedSkills.length
  const max = system.skillCount
  const isMet = count >= max

  return (
    <div className="wizard-body">
      <div>
        <div className="wizard-step-heading">Skill Proficiencies</div>
        <div className="wizard-step-sub">
          Choose up to {max} skill{max !== 1 ? 's' : ''} your character is proficient in.
          {background && ` Skills suggested by your background are highlighted.`}
        </div>
      </div>
      <div className="wizard-skill-grid">
        {system.skills.map((skill) => {
          const isSelected = draft.selectedSkills.includes(skill.id)
          const isSugg = suggested.has(skill.id)
          const disabled = !isSelected && isMet
          return (
            <button
              key={skill.id}
              type="button"
              className={`wizard-skill-chip${isSelected ? ' is-selected' : ''}${isSugg && !isSelected ? ' is-suggested' : ''}`}
              onClick={() => !disabled && onToggle(skill.id)}
              disabled={disabled}
              title={disabled ? `Max ${max} skills selected` : undefined}
            >
              {isSugg && !isSelected && <span style={{ fontSize: 9 }}>★</span>}
              {skill.name}
              {skill.stat && <span className="wizard-skill-stat">{skill.stat}</span>}
            </button>
          )
        })}
      </div>
      <div className={`wizard-selection-count${isMet ? ' wizard-selection-count--met' : ''}`}>
        {count} / {max} selected{isMet ? ' — you\'re all set!' : ''}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────
// Ability score constants (shared)
// ─────────────────────────────────────────────

const STANDARD_ARRAY = [15, 14, 13, 12, 10, 8]

const ABILITY_SCORE_DEFS = [
  { id: 'str' as const, abbr: 'STR', name: 'Strength',     hint: 'Melee attacks, Athletics, carrying capacity' },
  { id: 'dex' as const, abbr: 'DEX', name: 'Dexterity',    hint: 'Ranged attacks, AC, Stealth, Initiative' },
  { id: 'con' as const, abbr: 'CON', name: 'Constitution', hint: 'Hit points, concentration checks' },
  { id: 'int' as const, abbr: 'INT', name: 'Intelligence', hint: 'Arcana, History, Investigation, Wizard spells' },
  { id: 'wis' as const, abbr: 'WIS', name: 'Wisdom',       hint: 'Perception, Medicine, Insight, Cleric spells' },
  { id: 'cha' as const, abbr: 'CHA', name: 'Charisma',     hint: 'Persuasion, Deception, Bard/Sorcerer spells' },
]

function abilityMod(score: number | null): string {
  if (score === null) return '—'
  const m = Math.floor((score - 10) / 2)
  return m >= 0 ? `+${m}` : `${m}`
}

function StepAbilityScores({
  draft,
  onUpdate,
}: {
  draft: CharacterDraft
  onUpdate: (scores: AbilityScores) => void
}) {
  // Build a map: value → which stat currently holds it
  const takenBy = new Map<number, keyof AbilityScores>()
  for (const def of ABILITY_SCORE_DEFS) {
    const v = draft.abilityScores[def.id]
    if (v !== null) takenBy.set(v, def.id)
  }

  function assign(statId: keyof AbilityScores, value: number) {
    const prevHolder = takenBy.get(value)
    const prevValueOfThis = draft.abilityScores[statId]
    const next = { ...draft.abilityScores }
    // Swap: give the displaced stat the current stat's old value
    if (prevHolder && prevHolder !== statId) {
      next[prevHolder] = prevValueOfThis
    }
    next[statId] = value
    onUpdate(next)
  }

  const allAssigned = STANDARD_ARRAY.every((v) => takenBy.has(v))

  return (
    <div className="wizard-body">
      <div>
        <div className="wizard-step-heading">Ability Scores</div>
        <div className="wizard-step-sub">
          Assign the standard array (15, 14, 13, 12, 10, 8) to your six abilities. Click a value to assign it — clicking an already-placed value swaps the two stats.
        </div>
      </div>
      <div className="wizard-ability-grid">
        {ABILITY_SCORE_DEFS.map((def) => {
          const current = draft.abilityScores[def.id]
          return (
            <div
              key={def.id}
              className={`wizard-ability-row${current !== null ? ' has-value' : ''}`}
            >
              <div className="wizard-ability-label-col">
                <span className="wizard-ability-abbr">{def.abbr}</span>
                <span className="wizard-ability-name">{def.name}</span>
                <span className="wizard-ability-hint">{def.hint}</span>
              </div>
              <div className="wizard-ability-chips">
                {STANDARD_ARRAY.map((v) => {
                  const isCurrent = current === v
                  const isTaken = takenBy.has(v) && !isCurrent
                  return (
                    <button
                      key={v}
                      type="button"
                      className={`wizard-ability-chip${isCurrent ? ' is-selected' : ''}${isTaken ? ' is-taken' : ''}`}
                      onClick={() => assign(def.id, v)}
                      title={isTaken ? `Swap with ${takenBy.get(v)?.toUpperCase()}` : undefined}
                    >
                      {v}
                    </button>
                  )
                })}
                {current !== null && (
                  <span className="wizard-ability-mod">{abilityMod(current)}</span>
                )}
              </div>
            </div>
          )
        })}
      </div>
      <div className={`wizard-selection-count${allAssigned ? ' wizard-selection-count--met' : ''}`}>
        {STANDARD_ARRAY.filter((v) => takenBy.has(v)).length} / 6 assigned
        {allAssigned ? ' — all set!' : ''}
      </div>
    </div>
  )
}

function StepLanguages({
  draft,
  system,
  onToggle,
}: {
  draft: CharacterDraft
  system: WizardSystem
  onToggle: (lang: string) => void
}) {
  const max = system.languageCount ?? 2
  const languages = system.availableLanguages ?? []
  const bonusCount = draft.selectedLanguages.length

  return (
    <div className="wizard-body">
      <div>
        <div className="wizard-step-heading">Languages</div>
        <div className="wizard-step-sub">
          All characters speak <strong>Common</strong>. Choose {max} additional {max === 1 ? 'language' : 'languages'} from those available.
        </div>
      </div>
      <div className="wizard-skill-grid">
        {languages.map((lang) => {
          const isCommon = lang === 'Common'
          const isSelected = isCommon || draft.selectedLanguages.includes(lang)
          const disabled = !isSelected && bonusCount >= max
          return (
            <button
              key={lang}
              type="button"
              className={`wizard-skill-chip${isSelected ? ' is-selected' : ''}${isCommon ? ' is-auto-granted' : ''}`}
              onClick={() => !isCommon && !disabled && onToggle(lang)}
              disabled={isCommon || disabled}
              title={isCommon ? 'All characters know Common' : disabled ? `Max ${max} bonus languages` : undefined}
            >
              {isCommon && <span style={{ fontSize: 9 }}>★</span>}
              {lang}
            </button>
          )
        })}
      </div>
      <div className={`wizard-selection-count${bonusCount >= max ? ' wizard-selection-count--met' : ''}`}>
        {bonusCount} / {max} bonus {max === 1 ? 'language' : 'languages'} chosen
        {bonusCount >= max ? ' — all set!' : ''}
      </div>
    </div>
  )
}

function StepNameLevel({
  draft,
  system,
  onNameChange,
  onLevelChange,
}: {
  draft: CharacterDraft
  system: WizardSystem
  onNameChange: (v: string) => void
  onLevelChange: (v: number) => void
}) {
  const [min, max] = system.levelRange ?? [1, 20]

  return (
    <div className="wizard-body">
      <div>
        <div className="wizard-step-heading">Name your character</div>
        <div className="wizard-step-sub">The only thing you need to type.</div>
      </div>
      <div className="stack" style={{ gap: 8 }}>
        <label style={{ fontSize: 12, color: 'var(--muted-text)', fontWeight: 600 }}>Character Name</label>
        <input
          className="wizard-name-input"
          type="text"
          value={draft.name}
          onChange={(e) => onNameChange(e.target.value)}
          placeholder="Enter a name…"
          autoFocus
          maxLength={80}
        />
      </div>
      {system.levelRange && (
        <div className="stack" style={{ gap: 8 }}>
          <label style={{ fontSize: 12, color: 'var(--muted-text)', fontWeight: 600 }}>
            Starting Level
          </label>
          <div className="wizard-level-track">
            <span style={{ fontSize: 12, color: 'var(--muted-text)' }}>{min}</span>
            <input
              type="range"
              className="wizard-level-slider"
              min={min}
              max={max}
              value={draft.level}
              onChange={(e) => onLevelChange(Number(e.target.value))}
            />
            <span style={{ fontSize: 12, color: 'var(--muted-text)' }}>{max}</span>
            <span className="wizard-level-badge">{draft.level}</span>
          </div>
        </div>
      )}
    </div>
  )
}

function StepReview({
  draft,
  system,
  onJumpTo,
  onSubmit,
  busy,
  error,
}: {
  draft: CharacterDraft
  system: WizardSystem
  onJumpTo: (step: Step) => void
  onSubmit: () => void
  busy: boolean
  error: string | null
}) {
  const ancestry = system.ancestries?.find((a) => a.id === draft.ancestryId)
  const cls = system.classes.find((c) => c.id === draft.classId)
  const background = system.backgrounds.find((b) => b.id === draft.backgroundId)

  const personalityLines = []
  if (draft.virtue) personalityLines.push(`Virtue: ${DND_VIRTUES.find(v => v.id === draft.virtue)?.label ?? draft.virtue}`)
  if (draft.flaw) personalityLines.push(`Flaw: ${DND_FLAWS.find(f => f.id === draft.flaw)?.label ?? draft.flaw}`)
  if (draft.bond) personalityLines.push(`Bond: ${DND_BONDS.find(b => b.id === draft.bond)?.label ?? draft.bond}`)
  if (draft.simpleTrait) personalityLines.push(SIMPLE_TRAITS.find(t => t.id === draft.simpleTrait)?.label ?? draft.simpleTrait)

  const gearPackage = background
    ? { items: background.flavorGear }
    : system.gearPackages[0] ?? { items: [] }

  const missingName = !draft.name.trim()

  return (
    <div className="wizard-body">
      <div>
        <div className="wizard-step-heading">Review your character</div>
        <div className="wizard-step-sub">Everything look right? You can edit any section below.</div>
      </div>
      <div className="wizard-review-grid">
        <div className="wizard-review-row">
          <span className="wizard-review-label">Name</span>
          <span className="wizard-review-value" style={{ color: missingName ? 'var(--error, #e05a5a)' : undefined }}>
            {draft.name || '(missing — go back to Name step)'}
          </span>
          <button className="wizard-review-edit" onClick={() => onJumpTo('name-level')}>Edit</button>
        </div>
        <div className="wizard-review-row">
          <span className="wizard-review-label">System</span>
          <span className="wizard-review-value">{system.emoji} {system.name}</span>
          <button className="wizard-review-edit" onClick={() => onJumpTo('system')}>Edit</button>
        </div>
        {ancestry && (
          <div className="wizard-review-row">
            <span className="wizard-review-label">{system.ancestryLabel}</span>
            <span className="wizard-review-value">{ancestry.emoji} {ancestry.name}</span>
            <button className="wizard-review-edit" onClick={() => onJumpTo('ancestry')}>Edit</button>
          </div>
        )}
        {cls && (
          <div className="wizard-review-row">
            <span className="wizard-review-label">{system.classLabel}</span>
            <span className="wizard-review-value">{cls.emoji} {cls.name}</span>
            <button className="wizard-review-edit" onClick={() => onJumpTo('class')}>Edit</button>
          </div>
        )}
        {background && (
          <div className="wizard-review-row">
            <span className="wizard-review-label">Background</span>
            <span className="wizard-review-value">{background.name} — {background.description}</span>
            <button className="wizard-review-edit" onClick={() => onJumpTo('background-quiz')}>Edit</button>
          </div>
        )}
        {personalityLines.length > 0 && (
          <div className="wizard-review-row">
            <span className="wizard-review-label">Personality</span>
            <span className="wizard-review-value" style={{ whiteSpace: 'normal', lineHeight: 1.5 }}>
              {personalityLines.join(' · ')}
            </span>
            <button className="wizard-review-edit" onClick={() => onJumpTo('personality')}>Edit</button>
          </div>
        )}
        {Object.values(draft.abilityScores).some((v) => v !== null) && (
          <div className="wizard-review-row">
            <span className="wizard-review-label">Abilities</span>
            <span className="wizard-review-value" style={{ whiteSpace: 'normal', fontVariantNumeric: 'tabular-nums' }}>
              {(['str','dex','con','int','wis','cha'] as const)
                .filter((s) => draft.abilityScores[s] !== null)
                .map((s) => `${s.toUpperCase()} ${draft.abilityScores[s]}`)
                .join(' · ')}
            </span>
            <button className="wizard-review-edit" onClick={() => onJumpTo('ability-scores')}>Edit</button>
          </div>
        )}
        {draft.selectedSkills.length > 0 && (
          <div className="wizard-review-row">
            <span className="wizard-review-label">Skills</span>
            <span className="wizard-review-value" style={{ whiteSpace: 'normal' }}>
              {draft.selectedSkills.join(', ')}
            </span>
            <button className="wizard-review-edit" onClick={() => onJumpTo('skills')}>Edit</button>
          </div>
        )}
        {(draft.selectedLanguages.length > 0) && (
          <div className="wizard-review-row">
            <span className="wizard-review-label">Languages</span>
            <span className="wizard-review-value" style={{ whiteSpace: 'normal' }}>
              Common{draft.selectedLanguages.length > 0 ? `, ${draft.selectedLanguages.join(', ')}` : ''}
            </span>
            <button className="wizard-review-edit" onClick={() => onJumpTo('languages')}>Edit</button>
          </div>
        )}
        {gearPackage.items.length > 0 && (
          <div className="wizard-review-row">
            <span className="wizard-review-label">Starting Gear</span>
            <span className="wizard-review-value" style={{ whiteSpace: 'normal' }}>
              {gearPackage.items.join(', ')}
            </span>
            <span />
          </div>
        )}
        {system.levelRange && (
          <div className="wizard-review-row">
            <span className="wizard-review-label">Level</span>
            <span className="wizard-review-value">{draft.level}</span>
            <button className="wizard-review-edit" onClick={() => onJumpTo('name-level')}>Edit</button>
          </div>
        )}
      </div>

      {error && (
        <div className="inline-alert inline-alert-error">{error}</div>
      )}

      <button
        className="btn"
        type="button"
        disabled={busy || missingName}
        onClick={onSubmit}
        style={{ alignSelf: 'flex-start' }}
      >
        {busy ? 'Creating…' : 'Create Character'}
      </button>
    </div>
  )
}

// ─────────────────────────────────────────────
// Main wizard
// ─────────────────────────────────────────────

type Props = {
  onDone: () => void
  onCharacterCreated?: (characterId: number) => void
}

export default function CharacterWizard({ onDone, onCharacterCreated }: Props) {
  const [draft, setDraft] = useState<CharacterDraft>({ ...EMPTY_DRAFT })
  const [step, setStep] = useState<Step>('system')
  /** For background quiz: which question index is active */
  const [quizIndex, setQuizIndex] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const system = draft.systemId ? getSystem(draft.systemId) : undefined
  const steps = buildStepList(system)
  const stepIdx = steps.indexOf(step)

  // ── Navigation helpers ──────────────────────
  function goNext() {
    const next = steps[stepIdx + 1]
    if (next) {
      setStep(next)
      setQuizIndex(0)
    }
  }

  function goBack() {
    if (step === 'background-quiz' && quizIndex > 0) {
      setQuizIndex(quizIndex - 1)
      return
    }
    const prev = steps[stepIdx - 1]
    if (prev) setStep(prev)
  }

  function jumpTo(target: Step) {
    if (steps.includes(target)) setStep(target)
  }

  // ── Draft updaters ──────────────────────────
  function selectSystem(id: SystemId) {
    setDraft({ ...EMPTY_DRAFT, systemId: id, level: 1, abilityScores: { ...EMPTY_ABILITY_SCORES } })
    goNext()
  }

  function selectAncestry(id: string) {
    setDraft((d) => ({ ...d, ancestryId: id }))
    goNext()
  }

  function selectClass(id: string) {
    setDraft((d) => ({ ...d, classId: id }))
    goNext()
  }

  function answerQuiz(qId: string, optionId: string) {
    const newAnswers = { ...draft.quizAnswers, [qId]: optionId }
    setDraft((d) => ({ ...d, quizAnswers: newAnswers }))
    if (!system) return
    const isLastQuestion = quizIndex >= system.backgroundQuiz.length - 1
    if (isLastQuestion) {
      // auto-suggest background and advance to background pick sub-step
      const ranked = scoreBackgroundQuiz(system, newAnswers)
      setDraft((d) => ({
        ...d,
        quizAnswers: newAnswers,
        backgroundId: ranked[0] ?? null,
      }))
      // Move to a background-pick sub-step (we reuse background-quiz step with quizIndex=-1 sentinel)
      setQuizIndex(-1)
    } else {
      setQuizIndex(quizIndex + 1)
    }
  }

  function selectBackground(id: string) {
    setDraft((d) => ({ ...d, backgroundId: id }))
    // Pre-fill skills from this background
    const bg = system?.backgrounds.find((b) => b.id === id)
    if (bg && bg.suggestedSkills.length > 0) {
      const max = system?.skillCount ?? 2
      setDraft((d) => ({
        ...d,
        backgroundId: id,
        selectedSkills: bg.suggestedSkills.slice(0, max),
      }))
    }
    goNext()
  }

  function updatePersonality(key: 'virtue' | 'flaw' | 'bond' | 'simpleTrait', value: string) {
    setDraft((d) => ({ ...d, [key]: value }))
  }

  function updateAbilityScores(scores: AbilityScores) {
    setDraft((d) => ({ ...d, abilityScores: scores }))
  }

  function toggleLanguage(lang: string) {
    setDraft((d) => {
      const max = system?.languageCount ?? 2
      if (d.selectedLanguages.includes(lang)) {
        return { ...d, selectedLanguages: d.selectedLanguages.filter((l) => l !== lang) }
      }
      if (d.selectedLanguages.length >= max) return d
      return { ...d, selectedLanguages: [...d.selectedLanguages, lang] }
    })
  }

  function toggleSkill(skillId: string) {
    setDraft((d) => {
      const max = system?.skillCount ?? 4
      if (d.selectedSkills.includes(skillId)) {
        return { ...d, selectedSkills: d.selectedSkills.filter((s) => s !== skillId) }
      }
      if (d.selectedSkills.length >= max) return d
      return { ...d, selectedSkills: [...d.selectedSkills, skillId] }
    })
  }

  // ── Submit ──────────────────────────────────
  async function submit() {
    if (!draft.name.trim()) {
      setError('Please enter a character name.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const cls = system?.classes.find((c) => c.id === draft.classId)
      const ancestry = system?.ancestries?.find((a) => a.id === draft.ancestryId)
      const background = system?.backgrounds.find((b) => b.id === draft.backgroundId)
      const gearPackage = background
        ? background.flavorGear
        : system?.gearPackages[0]?.items ?? []

      const personality: Record<string, string | null> = {}
      if (system?.personalityFormat === 'dnd') {
        personality.virtue = DND_VIRTUES.find((v) => v.id === draft.virtue)?.label ?? null
        personality.flaw = DND_FLAWS.find((f) => f.id === draft.flaw)?.label ?? null
        personality.bond = DND_BONDS.find((b) => b.id === draft.bond)?.label ?? null
      } else {
        personality.trait = SIMPLE_TRAITS.find((t) => t.id === draft.simpleTrait)?.label ?? null
      }

      const sheet: Record<string, any> = {
        wizard_created: true,
        system: draft.systemId,
        ancestry: draft.ancestryId,
        background: draft.backgroundId,
        background_name: background?.name,
        personality,
        stats: Object.values(draft.abilityScores).some((v) => v !== null) ? draft.abilityScores : undefined,
        languages: draft.selectedLanguages.length > 0 ? ['Common', ...draft.selectedLanguages] : undefined,
        skills: draft.selectedSkills,
        inventory: gearPackage,
        quiz_answers: draft.quizAnswers,
        // Features & feats
        classFeatures: (cls?.level1Features ?? []).map((f) => f.name),
        racialFeatures: (ancestry?.traits ?? []).map((t) => t.name),
        feats: draft.selectedFeatIds.length > 0 ? draft.selectedFeatIds : undefined,
      }

      const res = await apiFetch('/characters/', {
        method: 'POST',
        body: JSON.stringify({
          name: draft.name.trim(),
          level: draft.level,
          class_name: cls?.name ?? draft.classId ?? null,
          sheet,
        }),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => null)
        throw new Error(err?.detail || 'Failed to create character')
      }

      const data = await res.json()
      onCharacterCreated?.(data?.id)
      onDone()
    } catch (e: any) {
      setError(e?.message || 'Something went wrong. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  // ── Can we advance? ─────────────────────────
  function canAdvance(): boolean {
    switch (step) {
      case 'system': return Boolean(draft.systemId)
      case 'ancestry': return Boolean(draft.ancestryId)
      case 'class': return Boolean(draft.classId)
      case 'ability-scores': return STANDARD_ARRAY.every((v) =>
        Object.values(draft.abilityScores).includes(v)
      )
      case 'background-quiz': return quizIndex === -1 ? Boolean(draft.backgroundId) : Boolean(draft.quizAnswers[system?.backgroundQuiz[quizIndex]?.id ?? ''])
      case 'personality': return true // optional
      case 'skills': return true // optional
      case 'feats': return true  // optional
      case 'features': return true // informational
      case 'languages': return draft.selectedLanguages.length >= (system?.languageCount ?? 2)
      case 'name-level': return Boolean(draft.name.trim())
      default: return true
    }
  }

  const isFirstStep = stepIdx === 0
  const isLastStep = step === 'review'

  // ── Render ──────────────────────────────────
  return (
    <section className="dashboard-panel stack">
      <PageHeader
        title="Character Wizard"
        subtitle="Answer a few quick questions and we'll build your character profile."
        actions={
          <button className="btn btn-quiet" type="button" onClick={onDone}>
            Cancel
          </button>
        }
      />

      <WizardProgress steps={steps} current={step} />

      <div className={`wizard-shell${system ? ' wizard-shell--with-preview' : ''}`}>
        <div className="card card-pad">
          {/* System step */}
          {step === 'system' && (
            <StepSystem draft={draft} onSelect={selectSystem} />
          )}

          {/* Ancestry step */}
          {step === 'ancestry' && system && (
            <StepAncestry draft={draft} system={system} onSelect={selectAncestry} />
          )}

          {/* Class step */}
          {step === 'class' && system && (
            <StepClass draft={draft} system={system} onSelect={selectClass} />
          )}

          {/* Ability scores step */}
          {step === 'ability-scores' && system && (
            <StepAbilityScores
              draft={draft}
              onUpdate={updateAbilityScores}
            />
          )}

          {/* Background quiz + pick */}
          {step === 'background-quiz' && system && (
            quizIndex >= 0 ? (
              <StepBackgroundQuiz
                draft={draft}
                system={system}
                quizIndex={quizIndex}
                onAnswer={answerQuiz}
              />
            ) : (
              <StepBackgroundPick
                draft={draft}
                system={system}
                onSelect={selectBackground}
              />
            )
          )}

          {/* Personality step */}
          {step === 'personality' && system && (
            <StepPersonality
              draft={draft}
              system={system}
              onUpdate={updatePersonality}
            />
          )}

          {/* Skills step */}
          {step === 'skills' && system && (
            <StepSkills
              draft={draft}
              system={system}
              onToggle={toggleSkill}
            />
          )}

          {/* Features step — informational display of class + ancestry features */}
          {step === 'features' && system && (
            <StepFeatures
              draft={draft}
              system={system}
            />
          )}

          {/* Feats step — optional feat picker */}
          {step === 'feats' && system && (
            <StepFeats
              draft={draft}
              system={system}
              onToggle={(id) => setDraft((d) => ({
                ...d,
                selectedFeatIds: d.selectedFeatIds.includes(id)
                  ? d.selectedFeatIds.filter((f) => f !== id)
                  : [...d.selectedFeatIds, id],
              }))}
            />
          )}

          {/* Languages step */}
          {step === 'languages' && system && (
            <StepLanguages
              draft={draft}
              system={system}
              onToggle={toggleLanguage}
            />
          )}

          {/* Name + Level step */}
          {step === 'name-level' && system && (
            <StepNameLevel
              draft={draft}
              system={system}
              onNameChange={(v) => setDraft((d) => ({ ...d, name: v }))}
              onLevelChange={(v) => setDraft((d) => ({ ...d, level: v }))}
            />
          )}

          {/* Review step */}
          {step === 'review' && system && (
            <StepReview
              draft={draft}
              system={system}
              onJumpTo={jumpTo}
              onSubmit={submit}
              busy={busy}
              error={error}
            />
          )}

          {/* Nav buttons — shown on all non-system, non-review steps */}
          {step !== 'system' && !isLastStep && (
            <div className="wizard-nav" style={{ marginTop: 16 }}>
              <button
                className="btn btn-secondary"
                type="button"
                onClick={goBack}
              >
                ← Back
              </button>
              {!isFirstStep && (
                <button
                  className="btn"
                  type="button"
                  disabled={!canAdvance()}
                  onClick={goNext}
                >
                  Next →
                </button>
              )}
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

        {/* Preview sidebar — shown once a system is chosen */}
        {system && (
          <CharacterPreview draft={draft} system={system} />
        )}
      </div>
    </section>
  )
}
