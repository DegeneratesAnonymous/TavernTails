/**
 * CampaignCreationWizard.tsx
 *
 * Four creation paths:
 *   Quick Start   — minimal form: genre + name, start immediately
 *   Guided Builder — narrative quiz that infers tone/genre (original flow)
 *   Import         — paste lore and backstory text
 *   Campaign Seeds — choose from a curated list of campaign templates
 *
 * All paths produce a Campaign Contract on the backend.
 */

import React, { useCallback, useEffect, useState } from 'react'
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

type CreationPath = 'quick' | 'guided' | 'import' | 'seeds'

type QuizStep = 'quiz' | 'name' | 'ruleset' | 'level' | 'review'

type Step =
  | 'path'           // path chooser (always first)
  | QuizStep         // guided builder steps
  | 'quick-details'  // quick start: genre + name
  | 'import-text'    // import: paste lore
  | 'import-name'    // import: name the campaign
  | 'seed-pick'      // seeds: choose template
  | 'seed-name'      // seeds: name the campaign

type CampaignDraft = {
  path: CreationPath | null
  quizAnswers: Record<string, string>
  name: string
  ruleset: string
  worldName: string
  startingLevel: number
  ownerRole: 'player' | 'dm'
  ownerCharacterId: string
  canonMode: 'guided_canon' | 'strict_canon' | 'flexible_canon'
  creativityLevel: 'conservative' | 'balanced' | 'expansive'
  playstyle: string
  // Quick Start
  quickGenre: string
  quickTone: string
  // Import
  importLore: string
  importBackstory: string
  // Seeds
  seedId: string
}

const EMPTY_DRAFT: CampaignDraft = {
  path: null,
  quizAnswers: {},
  name: '',
  ruleset: '',
  worldName: '',
  startingLevel: 1,
  ownerRole: 'player',
  ownerCharacterId: '',
  canonMode: 'guided_canon',
  creativityLevel: 'balanced',
  playstyle: 'balanced',
  quickGenre: 'fantasy',
  quickTone: 'balanced',
  importLore: '',
  importBackstory: '',
  seedId: '',
}

type CampaignCharacterOption = {
  id: number | string
  name: string
  level?: number
  class_name?: string | null
}

// ─────────────────────────────────────────────
// Guided builder step lists
// ─────────────────────────────────────────────

const GUIDED_STEPS: QuizStep[] = ['quiz', 'name', 'ruleset', 'level', 'review']

const STEP_LABELS: Record<QuizStep, string> = {
  quiz: 'Scenario',
  name: 'Name',
  ruleset: 'System',
  level: 'Level',
  review: 'Review',
}

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

// ─────────────────────────────────────────────
// Ruleset options (guided builder)
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
// Tone / genre label maps
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

const CANON_OPTIONS = [
  {
    id: 'guided_canon' as const,
    label: 'Guided Canon',
    summary: 'Use your setup as truth; invent compatible details when useful.',
  },
  {
    id: 'strict_canon' as const,
    label: 'Strict Canon',
    summary: 'Major lore, factions, gods, and history require approval first.',
  },
  {
    id: 'flexible_canon' as const,
    label: 'Flexible Canon',
    summary: 'Prioritize momentum and surprise while avoiding contradictions.',
  },
]

const CREATIVITY_OPTIONS = [
  {
    id: 'conservative' as const,
    label: 'Conservative',
    summary: 'Prefer existing material and add very little per scene.',
  },
  {
    id: 'balanced' as const,
    label: 'Balanced',
    summary: 'Blend setup fidelity with a steady pace of new details.',
  },
  {
    id: 'expansive' as const,
    label: 'Expansive',
    summary: 'Create more NPCs, locations, and subplots when they fit.',
  },
]

const PLAYSTYLE_OPTIONS = [
  { id: 'balanced', label: 'Balanced', summary: 'A mix of social, exploration, mystery, and danger.' },
  { id: 'roleplay-heavy', label: 'Roleplay Heavy', summary: 'NPC motive, relationships, and character drama lead.' },
  { id: 'slow-burn mystery', label: 'Slow-Burn Mystery', summary: 'Concrete clues, careful reveals, and open questions.' },
  { id: 'tactical combat', label: 'Tactical Combat', summary: 'Terrain, resources, and enemy intent matter.' },
  { id: 'survival exploration', label: 'Survival Exploration', summary: 'Weather, supplies, travel risk, and hard choices.' },
]

// ─────────────────────────────────────────────
// Quick Start genres
// ─────────────────────────────────────────────

type QuickGenreOption = {
  id: string
  label: string
  emoji: string
  tone: string
  summary: string
}

const QUICK_GENRES: QuickGenreOption[] = [
  { id: 'fantasy', label: 'Fantasy', emoji: '🏰', tone: 'heroic', summary: 'Magic, monsters, and ancient prophecies.' },
  { id: 'horror', label: 'Horror', emoji: '🕯️', tone: 'horror', summary: 'Dread, darkness, and things that should not be.' },
  { id: 'sci-fi', label: 'Sci-Fi', emoji: '🚀', tone: 'thriller', summary: 'Starships, strange worlds, and hard choices.' },
  { id: 'mystery', label: 'Mystery', emoji: '🔍', tone: 'grim', summary: 'Clues, lies, and someone who knows more than they say.' },
  { id: 'political', label: 'Political', emoji: '👑', tone: 'political', summary: 'Factions, ambition, and consequences that last.' },
  { id: 'post-apocalyptic', label: 'Survival', emoji: '🌋', tone: 'grim', summary: 'Resources run out. Trust is a luxury. Keep moving.' },
]

// ─────────────────────────────────────────────
// Seed type (mirrors backend CAMPAIGN_SEEDS)
// ─────────────────────────────────────────────

type CampaignSeed = {
  id: string
  title: string
  tagline: string
  genre: string
  tone: string
  themes: string[]
  setting_summary: string
  creation_posture: string
  emoji: string
}

// ─────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────

function pickRandomName(): string {
  return RANDOM_CAMPAIGN_NAMES[Math.floor(Math.random() * RANDOM_CAMPAIGN_NAMES.length)]
}

function ownerParticipationPayload(draft: CampaignDraft) {
  return {
    owner_role: draft.ownerRole,
    owner_character_id: draft.ownerRole === 'player' ? Number(draft.ownerCharacterId) : null,
  }
}

function interpretationPayload(draft: CampaignDraft) {
  return {
    canon_policy: draft.canonMode,
    ai_creativity_level: draft.creativityLevel,
    playstyle_profile: draft.playstyle,
  }
}

function InterpretationControls({
  draft,
  onChange,
}: {
  draft: CampaignDraft
  onChange: (patch: Partial<CampaignDraft>) => void
}) {
  return (
    <div className="wizard-contract-controls">
      <div>
        <div className="wizard-section-kicker">Campaign Contract</div>
        <div className="wizard-step-sub">These become persistent instructions for scenes, memory, canon, and validation.</div>
      </div>
      <div className="wizard-control-group">
        <div className="wizard-control-label">Canon</div>
        <div className="wizard-segmented">
          {CANON_OPTIONS.map((opt) => (
            <button
              key={opt.id}
              type="button"
              className={`wizard-segment${draft.canonMode === opt.id ? ' is-selected' : ''}`}
              onClick={() => onChange({ canonMode: opt.id })}
              title={opt.summary}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <div className="wizard-control-help">
          {CANON_OPTIONS.find((opt) => opt.id === draft.canonMode)?.summary}
        </div>
      </div>
      <div className="wizard-control-grid">
        <div className="wizard-control-group">
          <label className="wizard-control-label" htmlFor="campaign-creativity">AI Creativity</label>
          <select
            id="campaign-creativity"
            className="input"
            value={draft.creativityLevel}
            onChange={(e) => onChange({ creativityLevel: e.target.value as CampaignDraft['creativityLevel'] })}
          >
            {CREATIVITY_OPTIONS.map((opt) => (
              <option key={opt.id} value={opt.id}>{opt.label}</option>
            ))}
          </select>
          <div className="wizard-control-help">
            {CREATIVITY_OPTIONS.find((opt) => opt.id === draft.creativityLevel)?.summary}
          </div>
        </div>
        <div className="wizard-control-group">
          <label className="wizard-control-label" htmlFor="campaign-playstyle">Playstyle</label>
          <select
            id="campaign-playstyle"
            className="input"
            value={draft.playstyle}
            onChange={(e) => onChange({ playstyle: e.target.value })}
          >
            {PLAYSTYLE_OPTIONS.map((opt) => (
              <option key={opt.id} value={opt.id}>{opt.label}</option>
            ))}
          </select>
          <div className="wizard-control-help">
            {PLAYSTYLE_OPTIONS.find((opt) => opt.id === draft.playstyle)?.summary}
          </div>
        </div>
      </div>
    </div>
  )
}

function ContractPreview({ draft, posture }: { draft: CampaignDraft; posture: string }) {
  const canon = CANON_OPTIONS.find((opt) => opt.id === draft.canonMode)
  const creativity = CREATIVITY_OPTIONS.find((opt) => opt.id === draft.creativityLevel)
  const playstyle = PLAYSTYLE_OPTIONS.find((opt) => opt.id === draft.playstyle)
  return (
    <div className="wizard-contract-preview">
      <div className="wizard-section-kicker">Session Zero Preview</div>
      <div className="wizard-preview-list">
        <div><strong>Posture</strong><span>{posture}</span></div>
        <div><strong>Canon</strong><span>{canon?.label}</span></div>
        <div><strong>Creativity</strong><span>{creativity?.label}</span></div>
        <div><strong>Playstyle</strong><span>{playstyle?.label}</span></div>
      </div>
    </div>
  )
}

function SeatChoice({
  draft,
  characters,
  onChange,
}: {
  draft: CampaignDraft
  characters: CampaignCharacterOption[]
  onChange: (patch: Partial<CampaignDraft>) => void
}) {
  return (
    <div className="card card-pad" style={{ display: 'grid', gap: 10, marginTop: 14 }}>
      <div style={{ fontWeight: 750 }}>Your seat</div>
      <div className="row-wrap" style={{ gap: 8 }}>
        <label className="btn btn-secondary btn-sm" style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
          <input
            type="radio"
            checked={draft.ownerRole === 'player'}
            onChange={() => onChange({ ownerRole: 'player' })}
          />
          Join as character
        </label>
        <label className="btn btn-secondary btn-sm" style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
          <input
            type="radio"
            checked={draft.ownerRole === 'dm'}
            onChange={() => onChange({ ownerRole: 'dm', ownerCharacterId: '' })}
          />
          I am the DM
        </label>
      </div>
      {draft.ownerRole === 'player' ? (
        characters.length ? (
          <select
            className="input"
            value={draft.ownerCharacterId}
            onChange={(e) => onChange({ ownerCharacterId: e.target.value })}
          >
            <option value="">Select a character</option>
            {characters.map((character) => (
              <option key={character.id} value={String(character.id)}>
                {character.name} L{character.level ?? 1}{character.class_name ? ` ${character.class_name}` : ''}
              </option>
            ))}
          </select>
        ) : (
          <div className="inline-alert">Create or import a character first, or designate yourself as DM.</div>
        )
      ) : null}
    </div>
  )
}

// ─────────────────────────────────────────────
// Progress indicator (guided builder)
// ─────────────────────────────────────────────

function WizardProgress({ steps, current }: { steps: QuizStep[]; current: QuizStep }) {
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
// Step: Path chooser
// ─────────────────────────────────────────────

function StepPath({ onPick }: { onPick: (path: CreationPath) => void }) {
  const options: { id: CreationPath; label: string; emoji: string; desc: string }[] = [
    {
      id: 'quick',
      label: 'Quick Start',
      emoji: '⚡',
      desc: 'Pick a genre and name your campaign. TavernTails handles the rest.',
    },
    {
      id: 'guided',
      label: 'Guided Builder',
      emoji: '🧭',
      desc: 'Answer 5 short scenario questions and we\'ll shape the campaign to match your style.',
    },
    {
      id: 'import',
      label: 'Import My Campaign',
      emoji: '📖',
      desc: 'Paste your worldbuilding notes, lore documents, or homebrew text.',
    },
    {
      id: 'seeds',
      label: 'Campaign Seeds',
      emoji: '🌱',
      desc: 'Choose from 8 curated starting points — from frozen mysteries to city intrigue.',
    },
  ]

  return (
    <div className="wizard-body">
      <div>
        <div className="wizard-step-heading">How do you want to begin?</div>
        <div className="wizard-step-sub">Choose the creation style that fits you.</div>
      </div>
      <div className="wizard-path-grid">
        {options.map((opt) => (
          <button
            key={opt.id}
            type="button"
            className="wizard-path-card"
            onClick={() => onPick(opt.id)}
          >
            <span className="wizard-path-emoji">{opt.emoji}</span>
            <strong className="wizard-path-label">{opt.label}</strong>
            <span className="wizard-path-desc">{opt.desc}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────
// Step: Quick Start details
// ─────────────────────────────────────────────

function StepQuickDetails({
  draft,
  onNameChange,
  onGenreChange,
}: {
  draft: CampaignDraft
  onNameChange: (v: string) => void
  onGenreChange: (genre: string, tone: string) => void
}) {
  const randomizeName = useCallback(() => onNameChange(pickRandomName()), [onNameChange])

  return (
    <div className="wizard-body">
      <div>
        <div className="wizard-step-heading">Quick Start</div>
        <div className="wizard-step-sub">Choose a genre and name your campaign. TavernTails will generate the rest.</div>
      </div>

      <div className="stack" style={{ gap: 20 }}>
        <div>
          <label style={{ fontSize: 12, color: 'var(--muted-text)', fontWeight: 600, display: 'block', marginBottom: 8 }}>
            Genre
          </label>
          <div className="wizard-quick-genre-grid">
            {QUICK_GENRES.map((g) => (
              <button
                key={g.id}
                type="button"
                className={`wizard-option-card${draft.quickGenre === g.id ? ' is-selected' : ''}`}
                onClick={() => onGenreChange(g.id, g.tone)}
              >
                <span className="wizard-option-emoji">{g.emoji}</span>
                <span className="wizard-option-name">{g.label}</span>
                <span className="wizard-option-desc">{g.summary}</span>
              </button>
            ))}
          </div>
        </div>

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
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────
// Step: Import lore text
// ─────────────────────────────────────────────

function StepImportText({
  draft,
  onLoreChange,
  onBackstoryChange,
}: {
  draft: CampaignDraft
  onLoreChange: (v: string) => void
  onBackstoryChange: (v: string) => void
}) {
  return (
    <div className="wizard-body">
      <div>
        <div className="wizard-step-heading">Import Your Campaign</div>
        <div className="wizard-step-sub">
          Paste notes, lore, NPCs, factions, locations, or session prep. TavernTails will
          interpret what matters and ask you about anything ambiguous.
        </div>
      </div>

      <div className="stack" style={{ gap: 16 }}>
        <div className="stack" style={{ gap: 6 }}>
          <label style={{ fontSize: 12, color: 'var(--muted-text)', fontWeight: 600 }}>
            World Lore / Campaign Notes
          </label>
          <div style={{ fontSize: 11, color: 'var(--muted-text)', marginBottom: 4 }}>
            Tip: label entities for best results — e.g. <code>NPC: Velara Ashveil</code>,{' '}
            <code>Location: Thornwatch Keep</code>, <code>Faction: The Obsidian Council</code>
          </div>
          <textarea
            className="input"
            rows={10}
            value={draft.importLore}
            onChange={(e) => onLoreChange(e.target.value)}
            placeholder={
              'NPC: Velara Ashveil — leader of the Obsidian Council\n' +
              'Location: Thornwatch Keep — abandoned fortress on the northern pass\n' +
              'Faction: The Obsidian Council controls all sanctioned magic\n' +
              '\nThe players will arrive during a council succession crisis...'
            }
            style={{ resize: 'vertical', fontFamily: 'inherit' }}
          />
        </div>

        <div className="stack" style={{ gap: 6 }}>
          <label style={{ fontSize: 12, color: 'var(--muted-text)', fontWeight: 600 }}>
            Player Backstory <span style={{ fontWeight: 400 }}>(optional)</span>
          </label>
          <textarea
            className="input"
            rows={5}
            value={draft.importBackstory}
            onChange={(e) => onBackstoryChange(e.target.value)}
            placeholder={
              'Character: Kael — former soldier who deserted before the Siege of Thornwatch.\n' +
              'He owes a debt to a smuggler named Deva. His mentor disappeared two years ago.\n' +
              'Secret: Kael knows who ordered the massacre at Veldrath village.'
            }
            style={{ resize: 'vertical', fontFamily: 'inherit' }}
          />
          <div className="muted" style={{ fontSize: 11 }}>
            TavernTails extracts hooks, debts, secrets, and promises — with your consent before using them.
          </div>
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────
// Step: Seed picker
// ─────────────────────────────────────────────

function StepSeedPick({
  seeds,
  selected,
  onPick,
}: {
  seeds: CampaignSeed[]
  selected: string
  onPick: (id: string) => void
}) {
  if (!seeds.length) {
    return (
      <div className="wizard-body">
        <div className="wizard-step-heading">Campaign Seeds</div>
        <div className="muted">Loading seeds…</div>
      </div>
    )
  }

  return (
    <div className="wizard-body">
      <div>
        <div className="wizard-step-heading">Campaign Seeds</div>
        <div className="wizard-step-sub">Choose a curated starting point. You can still customise everything before launching.</div>
      </div>
      <div className="wizard-seed-grid">
        {seeds.map((seed) => (
          <button
            key={seed.id}
            type="button"
            className={`wizard-seed-card${selected === seed.id ? ' is-selected' : ''}`}
            onClick={() => onPick(seed.id)}
          >
            <span className="wizard-seed-emoji">{seed.emoji}</span>
            <strong className="wizard-seed-title">{seed.title}</strong>
            <span className="wizard-seed-tagline">{seed.tagline}</span>
            <span className="wizard-seed-tags">
              {seed.themes.slice(0, 3).map((t) => (
                <span key={t} className="wizard-mood-tag" style={{ fontSize: 10 }}>
                  {t}
                </span>
              ))}
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────
// Step: Seed name (after picking a seed)
// ─────────────────────────────────────────────

function StepSeedName({
  draft,
  seed,
  onNameChange,
}: {
  draft: CampaignDraft
  seed: CampaignSeed | null
  onNameChange: (v: string) => void
}) {
  const randomizeName = useCallback(() => onNameChange(pickRandomName()), [onNameChange])

  return (
    <div className="wizard-body">
      <div>
        <div className="wizard-step-heading">
          {seed ? `${seed.emoji} ${seed.title}` : 'Name your campaign'}
        </div>
        {seed && (
          <div className="wizard-step-sub" style={{ fontStyle: 'italic' }}>
            "{seed.tagline}"
          </div>
        )}
      </div>

      {seed && (
        <div className="card card-pad muted" style={{ fontSize: 13 }}>
          {seed.setting_summary}
        </div>
      )}

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
            placeholder={seed?.title ?? 'e.g. The Shattered Crown'}
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
        <div className="muted" style={{ fontSize: 11 }}>
          You can change this any time in campaign settings.
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────
// Import: Name step
// ─────────────────────────────────────────────

function StepImportName({
  draft,
  onNameChange,
}: {
  draft: CampaignDraft
  onNameChange: (v: string) => void
}) {
  const randomizeName = useCallback(() => onNameChange(pickRandomName()), [onNameChange])

  return (
    <div className="wizard-body">
      <div>
        <div className="wizard-step-heading">Name your campaign</div>
        <div className="wizard-step-sub">
          TavernTails will interpret your lore and generate a Campaign Contract after creation.
        </div>
      </div>
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
            placeholder="e.g. The Obsidian Council"
            autoFocus
            maxLength={100}
            style={{ flex: 1 }}
          />
          <button
            type="button"
            className="btn btn-secondary"
            onClick={randomizeName}
            title="Random name"
            style={{ flexShrink: 0, fontSize: 18, padding: '6px 12px', lineHeight: 1 }}
          >
            &#x21BA;
          </button>
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────
// Guided Builder Steps (unchanged logic)
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
  const randomizeName = useCallback(() => onNameChange(pickRandomName()), [onNameChange])

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
            Leave blank to decide later or let TavernTails suggest one.
          </div>
        </div>
      </div>
    </div>
  )
}

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
  onJumpTo: (step: QuizStep) => void
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
// API submission helpers
// ─────────────────────────────────────────────

async function submitQuickStart(draft: CampaignDraft): Promise<CreatedCampaignResult> {
  const res = await apiFetch('/campaigns', {
    method: 'POST',
    body: JSON.stringify({
      name: draft.name.trim(),
      description: '',
      create_session: true,
      ...ownerParticipationPayload(draft),
      creation_posture: 'player_fast_start',
      preferences: {
        genre: draft.quickGenre,
        tone: draft.quickTone,
        ...interpretationPayload(draft),
      },
    }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => null)
    throw new Error(err?.detail || 'Failed to create campaign')
  }
  const body = await res.json()
  return parseCreatedCampaign(body)
}

async function submitImport(draft: CampaignDraft): Promise<CreatedCampaignResult> {
  const backstoryEntries = draft.importBackstory.trim()
    ? [{ character_name: 'Player Character', text: draft.importBackstory.trim() }]
    : []

  const res = await apiFetch('/campaigns', {
    method: 'POST',
    body: JSON.stringify({
      name: draft.name.trim(),
      description: '',
      create_session: true,
      ...ownerParticipationPayload(draft),
      creation_posture: 'lore_importer',
      imported_lore_summary: draft.importLore.trim() || null,
      player_backstories: backstoryEntries,
      preferences: {
        ...interpretationPayload(draft),
        setting_summary: draft.importLore.trim().slice(0, 500),
      },
    }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => null)
    throw new Error(err?.detail || 'Failed to create campaign')
  }
  const body = await res.json()
  return parseCreatedCampaign(body)
}

async function submitSeed(draft: CampaignDraft, seed: CampaignSeed): Promise<CreatedCampaignResult> {
  const res = await apiFetch('/campaigns', {
    method: 'POST',
    body: JSON.stringify({
      name: (draft.name.trim() || seed.title),
      description: seed.setting_summary,
      create_session: true,
      ...ownerParticipationPayload(draft),
      creation_posture: seed.creation_posture,
      seed_id: seed.id,
      preferences: {
        genre: seed.genre,
        tone: seed.tone,
        ...interpretationPayload(draft),
      },
    }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => null)
    throw new Error(err?.detail || 'Failed to create campaign')
  }
  const body = await res.json()
  return parseCreatedCampaign(body)
}

async function submitGuided(draft: CampaignDraft, derived: ReturnType<typeof deriveCampaignSettings>): Promise<CreatedCampaignResult> {
  const createRes = await apiFetch('/campaigns', {
    method: 'POST',
    body: JSON.stringify({
      name: draft.name.trim(),
      description: derived.setting_summary,
      create_session: true,
      ...ownerParticipationPayload(draft),
      creation_posture: 'guided_builder',
      preferences: {
        genre: derived.genre,
        tone: derived.tone,
        pacing: derived.pacing,
        ...interpretationPayload(draft),
        setting_summary: derived.setting_summary,
        world_name: draft.worldName.trim() || '',
        ruleset: draft.ruleset,
        starting_level: draft.startingLevel,
      },
    }),
  })
  if (!createRes.ok) {
    const err = await createRes.json().catch(() => null)
    throw new Error(err?.detail || 'Failed to create campaign')
  }
  const body = await createRes.json()
  const created = parseCreatedCampaign(body)

  await apiFetch(`/campaigns/${created.campaignId}/settings`, {
    method: 'PUT',
    body: JSON.stringify({
      world_name: draft.worldName.trim() || '',
      setting_summary: derived.setting_summary,
      tone: derived.tone,
      ruleset: draft.ruleset,
      starting_level: draft.startingLevel,
      house_rules: '',
      canon_policy: draft.canonMode,
      ai_creativity_level: draft.creativityLevel,
      playstyle_profile: draft.playstyle,
    }),
  })

  return created
}

// ─────────────────────────────────────────────
// Main wizard
// ─────────────────────────────────────────────

type Props = {
  onDone: () => void
  onCampaignCreated?: (campaignId: string, sessionId?: string | null, ownerCharacterId?: number | null) => void
  characters?: CampaignCharacterOption[]
}

type CreatedCampaignResult = {
  campaignId: string
  sessionId: string | null
}

function parseCreatedCampaign(body: any): CreatedCampaignResult {
  const campaign = body?.campaign ?? body
  const campaignId = campaign?.id ?? campaign?.campaign_id
  if (!campaignId) throw new Error('Campaign created but ID not returned')
  const sessions = Array.isArray(campaign?.sessions) ? campaign.sessions : []
  const sessionId = sessions[0]?.id ? String(sessions[0].id) : null
  return { campaignId: String(campaignId), sessionId }
}

export default function CampaignCreationWizard({ onDone, onCampaignCreated, characters = [] }: Props) {
  const [draft, setDraft] = useState<CampaignDraft>({ ...EMPTY_DRAFT })
  const [step, setStep] = useState<Step>('path')
  const [quizIndex, setQuizIndex] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [seeds, setSeeds] = useState<CampaignSeed[]>([])

  const derived = deriveCampaignSettings(draft.quizAnswers)

  // Lazy-load seeds when user picks that path
  useEffect(() => {
    if (step === 'seed-pick' && !seeds.length) {
      apiFetch('/campaigns/seeds')
        .then((r) => r.json())
        .then((d) => setSeeds(d.seeds ?? []))
        .catch(() => {})
    }
  }, [step, seeds.length])

  const activeSeed = seeds.find((s) => s.id === draft.seedId) ?? null

  // ── Guided Builder navigation ──────────────
  const guidedIdx = GUIDED_STEPS.indexOf(step as QuizStep)

  function goNextGuided() {
    const next = GUIDED_STEPS[guidedIdx + 1]
    if (next) setStep(next)
  }

  function goBackGuided() {
    if (step === 'quiz' && quizIndex > 0) {
      setQuizIndex(quizIndex - 1)
      return
    }
    if (step === 'quiz') {
      setStep('path')
      return
    }
    const prev = GUIDED_STEPS[guidedIdx - 1]
    if (prev) setStep(prev)
  }

  function jumpToGuided(target: QuizStep) {
    setStep(target)
    if (target === 'quiz') setQuizIndex(0)
  }

  function answerQuiz(qId: string, optionId: string) {
    setDraft((d) => ({ ...d, quizAnswers: { ...d.quizAnswers, [qId]: optionId } }))
    const isLast = quizIndex >= CAMPAIGN_QUIZ.length - 1
    if (isLast) {
      goNextGuided()
    } else {
      setQuizIndex(quizIndex + 1)
    }
  }

  // ── Path chooser ───────────────────────────
  function pickPath(path: CreationPath) {
    setDraft((d) => ({ ...d, path }))
    setError(null)
    switch (path) {
      case 'quick':   setStep('quick-details'); break
      case 'guided':  setStep('quiz');          break
      case 'import':  setStep('import-text');   break
      case 'seeds':   setStep('seed-pick');     break
    }
  }

  // ── Submit ─────────────────────────────────
  async function submit() {
    setBusy(true)
    setError(null)
    try {
      if (draft.ownerRole === 'player' && !draft.ownerCharacterId) {
        setError('Choose which character you are joining with, or designate yourself as DM.')
        setBusy(false)
        return
      }
      let created: CreatedCampaignResult
      switch (draft.path) {
        case 'quick':
          if (!draft.name.trim()) { setError('Please enter a campaign name.'); setBusy(false); return }
          created = await submitQuickStart(draft)
          break
        case 'import':
          if (!draft.name.trim()) { setError('Please enter a campaign name.'); setBusy(false); return }
          if (!draft.importLore.trim()) { setError('Please paste some lore or notes to import.'); setBusy(false); return }
          created = await submitImport(draft)
          break
        case 'seeds':
          if (!activeSeed) { setError('Please select a campaign seed.'); setBusy(false); return }
          created = await submitSeed(draft, activeSeed)
          break
        case 'guided':
        default:
          if (!draft.name.trim()) { setError('Please enter a campaign name.'); setBusy(false); return }
          if (!draft.ruleset) { setError('Please select a game system.'); setBusy(false); return }
          created = await submitGuided(draft, derived)
          break
      }
      onCampaignCreated?.(
        created.campaignId,
        created.sessionId,
        draft.ownerRole === 'player' && draft.ownerCharacterId ? Number(draft.ownerCharacterId) : null,
      )
      onDone()
    } catch (e: any) {
      setError(e?.message || 'Something went wrong. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  // ── Can advance? ───────────────────────────
  function canAdvance(): boolean {
    switch (step) {
      case 'quiz':          return Boolean(draft.quizAnswers[CAMPAIGN_QUIZ[quizIndex]?.id ?? ''])
      case 'name':          return Boolean(draft.name.trim())
      case 'ruleset':       return Boolean(draft.ruleset)
      case 'quick-details': return Boolean(draft.name.trim() && draft.quickGenre)
      case 'import-text':   return Boolean(draft.importLore.trim())
      case 'import-name':   return Boolean(draft.name.trim())
      case 'seed-pick':     return Boolean(draft.seedId)
      case 'seed-name':     return Boolean(draft.name.trim() || activeSeed?.title)
      default:              return true
    }
  }

  // ── Back navigation ────────────────────────
  function goBack() {
    switch (step) {
      case 'quick-details': setStep('path'); break
      case 'import-text':   setStep('path'); break
      case 'import-name':   setStep('import-text'); break
      case 'seed-pick':     setStep('path'); break
      case 'seed-name':     setStep('seed-pick'); break
      default:
        if (draft.path === 'guided') goBackGuided()
        break
    }
  }

  // ── Title ──────────────────────────────────
  const title = (() => {
    if (step === 'path') return 'New Campaign'
    if (draft.path === 'guided') return 'Guided Builder'
    if (draft.path === 'import') return 'Import Campaign'
    if (draft.path === 'seeds') return 'Campaign Seeds'
    return 'Quick Start'
  })()

  const isFirstStep = step === 'path'
  const showProgress = draft.path === 'guided' && step !== 'path'

  return (
    <section className="dashboard-panel stack">
      <PageHeader
        title={title}
        subtitle={isFirstStep ? 'Choose a creation style to begin.' : undefined}
        actions={
          <button className="btn btn-quiet" type="button" onClick={onDone}>
            Cancel
          </button>
        }
      />

      {showProgress && (
        <WizardProgress steps={GUIDED_STEPS} current={step as QuizStep} />
      )}

      <div className="card card-pad" style={{ maxWidth: 680 }}>

        {/* Path chooser */}
        {step === 'path' && (
          <StepPath onPick={pickPath} />
        )}

        {/* Quick Start */}
        {step === 'quick-details' && (
          <>
            <StepQuickDetails
              draft={draft}
              onNameChange={(v) => setDraft((d) => ({ ...d, name: v }))}
              onGenreChange={(genre, tone) => setDraft((d) => ({ ...d, quickGenre: genre, quickTone: tone }))}
            />
            <InterpretationControls
              draft={draft}
              onChange={(patch) => setDraft((d) => ({ ...d, ...patch }))}
            />
            <ContractPreview draft={draft} posture="Player Fast Start" />
            <SeatChoice
              draft={draft}
              characters={characters}
              onChange={(patch) => setDraft((d) => ({ ...d, ...patch }))}
            />
            {error && <div className="inline-alert inline-alert-error" style={{ marginTop: 12 }}>{error}</div>}
            <div className="wizard-nav" style={{ marginTop: 16 }}>
              <button className="btn btn-secondary" type="button" onClick={goBack}>← Back</button>
              <button className="btn" type="button" disabled={!canAdvance() || busy} onClick={submit}>
                {busy ? 'Creating…' : 'Create Campaign →'}
              </button>
            </div>
          </>
        )}

        {/* Guided Builder — Quiz */}
        {step === 'quiz' && (
          <>
            <StepQuiz draft={draft} questionIndex={quizIndex} onAnswer={answerQuiz} />
            <div className="wizard-nav" style={{ marginTop: 16, justifyContent: 'flex-start' }}>
              <button className="btn btn-secondary" type="button" onClick={goBack}>← Back</button>
            </div>
          </>
        )}

        {/* Guided Builder — Name */}
        {step === 'name' && (
          <>
            <StepName
              draft={draft}
              derived={derived}
              onNameChange={(v) => setDraft((d) => ({ ...d, name: v }))}
              onWorldNameChange={(v) => setDraft((d) => ({ ...d, worldName: v }))}
            />
            <div className="wizard-nav" style={{ marginTop: 16 }}>
              <button className="btn btn-secondary" type="button" onClick={goBack}>← Back</button>
              <button className="btn" type="button" disabled={!canAdvance()} onClick={goNextGuided}>Next →</button>
            </div>
          </>
        )}

        {/* Guided Builder — Ruleset */}
        {step === 'ruleset' && (
          <>
            <StepRuleset
              draft={draft}
              onSelect={(id) => {
                setDraft((d) => ({ ...d, ruleset: id }))
                goNextGuided()
              }}
            />
            <div className="wizard-nav" style={{ marginTop: 16, justifyContent: 'flex-start' }}>
              <button className="btn btn-secondary" type="button" onClick={goBack}>← Back</button>
            </div>
          </>
        )}

        {/* Guided Builder — Level */}
        {step === 'level' && (
          <>
            <StepLevel
              draft={draft}
              onLevelChange={(v) => setDraft((d) => ({ ...d, startingLevel: v }))}
            />
            <div className="wizard-nav" style={{ marginTop: 16 }}>
              <button className="btn btn-secondary" type="button" onClick={goBack}>← Back</button>
              <button className="btn" type="button" disabled={!canAdvance()} onClick={goNextGuided}>Next →</button>
            </div>
          </>
        )}

        {/* Guided Builder — Review */}
        {step === 'review' && (
          <>
            <StepReview
              draft={draft}
              derived={derived}
              onJumpTo={jumpToGuided}
              onSubmit={submit}
              busy={busy}
              error={error}
            />
            <InterpretationControls
              draft={draft}
              onChange={(patch) => setDraft((d) => ({ ...d, ...patch }))}
            />
            <ContractPreview draft={draft} posture="Guided Builder" />
            <SeatChoice
              draft={draft}
              characters={characters}
              onChange={(patch) => setDraft((d) => ({ ...d, ...patch }))}
            />
            <div className="wizard-nav" style={{ marginTop: 8 }}>
              <button className="btn btn-secondary" type="button" onClick={goBack}>← Back</button>
            </div>
          </>
        )}

        {/* Import — Lore text */}
        {step === 'import-text' && (
          <>
            <StepImportText
              draft={draft}
              onLoreChange={(v) => setDraft((d) => ({ ...d, importLore: v }))}
              onBackstoryChange={(v) => setDraft((d) => ({ ...d, importBackstory: v }))}
            />
            <div className="wizard-nav" style={{ marginTop: 16 }}>
              <button className="btn btn-secondary" type="button" onClick={goBack}>← Back</button>
              <button
                className="btn"
                type="button"
                disabled={!canAdvance()}
                onClick={() => setStep('import-name')}
              >
                Next →
              </button>
            </div>
          </>
        )}

        {/* Import — Name */}
        {step === 'import-name' && (
          <>
            <StepImportName
              draft={draft}
              onNameChange={(v) => setDraft((d) => ({ ...d, name: v }))}
            />
            <InterpretationControls
              draft={draft}
              onChange={(patch) => setDraft((d) => ({ ...d, ...patch }))}
            />
            <ContractPreview draft={draft} posture="Lore Importer" />
            <SeatChoice
              draft={draft}
              characters={characters}
              onChange={(patch) => setDraft((d) => ({ ...d, ...patch }))}
            />
            {error && <div className="inline-alert inline-alert-error" style={{ marginTop: 12 }}>{error}</div>}
            <div className="wizard-nav" style={{ marginTop: 16 }}>
              <button className="btn btn-secondary" type="button" onClick={() => setStep('import-text')}>← Back</button>
              <button className="btn" type="button" disabled={!draft.name.trim() || busy} onClick={submit}>
                {busy ? 'Importing…' : 'Import & Create →'}
              </button>
            </div>
          </>
        )}

        {/* Seeds — Picker */}
        {step === 'seed-pick' && (
          <>
            <StepSeedPick
              seeds={seeds}
              selected={draft.seedId}
              onPick={(id) => {
                setDraft((d) => ({ ...d, seedId: id, name: d.name || '' }))
                setStep('seed-name')
              }}
            />
            <div className="wizard-nav" style={{ marginTop: 16, justifyContent: 'flex-start' }}>
              <button className="btn btn-secondary" type="button" onClick={goBack}>← Back</button>
            </div>
          </>
        )}

        {/* Seeds — Name */}
        {step === 'seed-name' && (
          <>
            <StepSeedName
              draft={draft}
              seed={activeSeed}
              onNameChange={(v) => setDraft((d) => ({ ...d, name: v }))}
            />
            <InterpretationControls
              draft={draft}
              onChange={(patch) => setDraft((d) => ({ ...d, ...patch }))}
            />
            <ContractPreview draft={draft} posture={activeSeed?.creation_posture || 'Campaign Seed'} />
            <SeatChoice
              draft={draft}
              characters={characters}
              onChange={(patch) => setDraft((d) => ({ ...d, ...patch }))}
            />
            {error && <div className="inline-alert inline-alert-error" style={{ marginTop: 12 }}>{error}</div>}
            <div className="wizard-nav" style={{ marginTop: 16 }}>
              <button className="btn btn-secondary" type="button" onClick={goBack}>← Back</button>
              <button className="btn" type="button" disabled={busy} onClick={submit}>
                {busy ? 'Creating…' : 'Create Campaign →'}
              </button>
            </div>
          </>
        )}
      </div>
    </section>
  )
}
