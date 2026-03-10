/**
 * wizard-data.ts
 * Static content for the Character Creation Wizard and Campaign Creation Wizard.
 * All 10 supported TavernTails game systems are covered.
 */

import {
  DND5E_FEATS,
  DND5E_CLASS_FEATURES,
  DND5E_ANCESTRY_TRAITS,
  DND5E_HIT_DICE,
  DND5E_SPELLS,
  SPELLCASTER_CLASS_IDS,
  type FeatOption,
  type ClassFeature,
  type AncestryTrait,
  type SpellOption,
} from './dnd5e-srd'

// Re-export SRD types so consumers can import from a single data module
export type { FeatOption, ClassFeature, AncestryTrait, SpellOption }
export { SPELLCASTER_CLASS_IDS }

// ─────────────────────────────────────────────
// Shared types
// ─────────────────────────────────────────────

export type SystemId =
  | 'dnd5e'
  | 'pf2e'
  | 'pf1e'
  | 'starfinder'
  | 'coc'
  | 'startrek'
  | 'sotdl'
  | 'wfrp'
  | 'alien'
  | 'shadowrun'

export type AncestryOption = {
  id: string
  name: string
  emoji: string
  description: string
  /** Key racial/species traits (mechanical, not flavor) */
  traits?: AncestryTrait[]
}

export type ClassOption = {
  id: string
  name: string
  emoji: string
  description: string
  /** Hit die size (e.g. 12 for Barbarian) */
  hitDie?: number
  /** Proficiencies granted by this class for saves, e.g. ['STR', 'CON'] */
  saveProficiencies?: string[]
  /** Features gained at level 1 (and level 2 for Artificer) */
  level1Features?: ClassFeature[]
}

export type BackgroundQuizQuestion = {
  id: string
  prompt: string
  options: {
    id: string
    text: string
    /** backgroundId → weight added to that background's score */
    scores: Record<string, number>
  }[]
}

export type BackgroundOutcome = {
  id: string
  name: string
  description: string
  suggestedSkills: string[]
  flavorGear: string[]
}

export type SkillOption = {
  id: string
  name: string
  stat?: string // governing stat abbreviation
}

export type GearPackage = {
  id: string
  name: string
  items: string[]
}

export type WizardSystem = {
  id: SystemId
  name: string
  emoji: string
  genre: string
  blurb: string
  /** Label shown above the ancestry picker. null = no ancestry step (all-human systems). */
  ancestryLabel: string | null
  ancestries: AncestryOption[] | null
  /** Label shown above the class picker */
  classLabel: string
  classes: ClassOption[]
  /** Label shown for the background section */
  backgroundLabel: string
  backgroundQuiz: BackgroundQuizQuestion[]
  backgrounds: BackgroundOutcome[]
  /** 'dnd' = virtue/flaw/bond, 'simple' = single trait pick, 'none' = skip */
  personalityFormat: 'dnd' | 'simple' | 'none'
  skills: SkillOption[]
  /** How many skills the player selects */
  skillCount: number
  gearPackages: GearPackage[]
  /** null = system has no level concept (CoC, WFRP, Alien) */
  levelRange: [number, number] | null
  /** If set, shows an ability score assignment step using the standard array */
  abilityScoreMethod?: 'standard_array'
  /** Languages available to pick from; undefined = no language step */
  availableLanguages?: string[]
  /** Number of bonus languages the player chooses (beyond auto-granted Common etc.) */
  languageCount?: number
  /** Feats available for selection during character creation */
  feats?: FeatOption[]
  /** How many feats the player may choose at character creation (0 = optional/variant) */
  featCountOnCreate?: number
  /** Spells available for selection during creation; filtered per class at runtime */
  availableSpells?: SpellOption[]
  /** How many spells the player picks at creation (default 4) */
  spellCountOnCreate?: number
}

// ─────────────────────────────────────────────
// Personality quick-picks (shared concepts)
// ─────────────────────────────────────────────

export type PersonalityPick = { id: string; label: string }

export const DND_VIRTUES: PersonalityPick[] = [
  { id: 'brave', label: 'Brave' },
  { id: 'wise', label: 'Wise' },
  { id: 'kind', label: 'Kind' },
  { id: 'just', label: 'Just' },
  { id: 'clever', label: 'Clever' },
  { id: 'free', label: 'Free-spirited' },
]

export const DND_FLAWS: PersonalityPick[] = [
  { id: 'reckless', label: 'Reckless' },
  { id: 'stubborn', label: 'Stubborn' },
  { id: 'greedy', label: 'Greedy' },
  { id: 'secretive', label: 'Secretive' },
  { id: 'proud', label: 'Proud' },
  { id: 'fearful', label: 'Fearful' },
]

export const DND_BONDS: PersonalityPick[] = [
  { id: 'family', label: 'My family' },
  { id: 'cause', label: 'A cause I serve' },
  { id: 'debt', label: 'A debt I owe' },
  { id: 'secret', label: 'A secret I keep' },
  { id: 'place', label: 'A place I protect' },
  { id: 'power', label: 'Power I seek' },
]

export const SIMPLE_TRAITS: PersonalityPick[] = [
  { id: 'cautious', label: 'Cautious & deliberate' },
  { id: 'bold', label: 'Bold & decisive' },
  { id: 'compassionate', label: 'Compassionate & empathetic' },
  { id: 'analytical', label: 'Analytical & methodical' },
  { id: 'irreverent', label: 'Irreverent & humorous' },
  { id: 'stoic', label: 'Stoic & duty-bound' },
]

// ─────────────────────────────────────────────
// D&D 5e
// ─────────────────────────────────────────────

const DND5E: WizardSystem = {
  id: 'dnd5e',
  name: 'D&D 5e',
  emoji: '⚔️',
  genre: 'Heroic Fantasy',
  blurb: 'Classic high fantasy with six ability scores, advantage/disadvantage, and rich class variety.',
  ancestryLabel: 'Race / Species',
  ancestries: [
    { id: 'human',     name: 'Human',        emoji: '🧑',  description: 'Adaptable and ambitious — extra skill or feat at 1st level.',                       traits: DND5E_ANCESTRY_TRAITS['human'] },
    { id: 'elf',       name: 'Elf',          emoji: '🧝',  description: 'Graceful and long-lived, with keen senses and trance instead of sleep.',          traits: DND5E_ANCESTRY_TRAITS['elf'] },
    { id: 'dwarf',     name: 'Dwarf',        emoji: '⛏️', description: 'Hardy and resilient, resistant to poison and gifted in stonework.',               traits: DND5E_ANCESTRY_TRAITS['dwarf'] },
    { id: 'halfling',  name: 'Halfling',     emoji: '🌿',  description: 'Lucky and nimble — can reroll 1s and are naturally stealthy.',                   traits: DND5E_ANCESTRY_TRAITS['halfling'] },
    { id: 'gnome',     name: 'Gnome',        emoji: '🔮',  description: 'Inventive and eccentric, with natural resistance to magic.',                     traits: DND5E_ANCESTRY_TRAITS['gnome'] },
    { id: 'half-elf',  name: 'Half-Elf',     emoji: '🌓',  description: 'Bridge between worlds — bonus skills and versatile ability bonuses.',            traits: DND5E_ANCESTRY_TRAITS['half-elf'] },
    { id: 'half-orc',  name: 'Half-Orc',     emoji: '💪',  description: 'Fierce and determined — Relentless Endurance keeps you alive.',                  traits: DND5E_ANCESTRY_TRAITS['half-orc'] },
    { id: 'tiefling',  name: 'Tiefling',     emoji: '😈',  description: 'Marked by infernal heritage — innate fire magic and dark charisma.',             traits: DND5E_ANCESTRY_TRAITS['tiefling'] },
    { id: 'dragonborn',name: 'Dragonborn',   emoji: '🐉',  description: 'Born of draconic power with a breath weapon and damage resistance.',             traits: DND5E_ANCESTRY_TRAITS['dragonborn'] },
    { id: 'other',     name: 'Other / Custom',emoji: '✨', description: 'Aasimar, Tabaxi, Warforged, or any homebrew species.',                          traits: DND5E_ANCESTRY_TRAITS['other'] },
  ],
  classLabel: 'Class',
  classes: [
    { id: 'artificer', name: 'Artificer', emoji: '🔧', description: 'Inventor and magic-item craftsperson.',               hitDie: DND5E_HIT_DICE['artificer'], saveProficiencies: ['CON', 'INT'], level1Features: DND5E_CLASS_FEATURES['artificer'] },
    { id: 'barbarian', name: 'Barbarian', emoji: '🪓', description: 'Raging warrior who shrugs off pain.',                 hitDie: DND5E_HIT_DICE['barbarian'], saveProficiencies: ['STR', 'CON'], level1Features: DND5E_CLASS_FEATURES['barbarian'] },
    { id: 'bard',      name: 'Bard',      emoji: '🎵', description: 'Performer and jack-of-all-trades spellcaster.',       hitDie: DND5E_HIT_DICE['bard'],      saveProficiencies: ['DEX', 'CHA'], level1Features: DND5E_CLASS_FEATURES['bard'] },
    { id: 'cleric',    name: 'Cleric',    emoji: '✝️', description: 'Divine channeler, healer, and warrior of faith.',    hitDie: DND5E_HIT_DICE['cleric'],    saveProficiencies: ['WIS', 'CHA'], level1Features: DND5E_CLASS_FEATURES['cleric'] },
    { id: 'druid',     name: 'Druid',     emoji: '🌿', description: 'Nature mystic who shapeshifts and calls the wild.',   hitDie: DND5E_HIT_DICE['druid'],     saveProficiencies: ['INT', 'WIS'], level1Features: DND5E_CLASS_FEATURES['druid'] },
    { id: 'fighter',   name: 'Fighter',   emoji: '🛡️', description: 'Martial expert with unmatched combat versatility.',  hitDie: DND5E_HIT_DICE['fighter'],   saveProficiencies: ['STR', 'CON'], level1Features: DND5E_CLASS_FEATURES['fighter'] },
    { id: 'monk',      name: 'Monk',      emoji: '👊', description: 'Discipline-trained master of unarmed combat and ki.',hitDie: DND5E_HIT_DICE['monk'],      saveProficiencies: ['STR', 'DEX'], level1Features: DND5E_CLASS_FEATURES['monk'] },
    { id: 'paladin',   name: 'Paladin',   emoji: '⚜️', description: 'Holy warrior bound to an oath and smiting evil.',   hitDie: DND5E_HIT_DICE['paladin'],   saveProficiencies: ['WIS', 'CHA'], level1Features: DND5E_CLASS_FEATURES['paladin'] },
    { id: 'ranger',    name: 'Ranger',    emoji: '🏹', description: 'Wilderness tracker and hunter with a companion option.', hitDie: DND5E_HIT_DICE['ranger'], saveProficiencies: ['STR', 'DEX'], level1Features: DND5E_CLASS_FEATURES['ranger'] },
    { id: 'rogue',     name: 'Rogue',     emoji: '🗡️', description: 'Cunning and deadly — Sneak Attack and Expertise.',   hitDie: DND5E_HIT_DICE['rogue'],     saveProficiencies: ['DEX', 'INT'], level1Features: DND5E_CLASS_FEATURES['rogue'] },
    { id: 'sorcerer',  name: 'Sorcerer',  emoji: '✨', description: 'Innate magical power shaped by bloodline.',           hitDie: DND5E_HIT_DICE['sorcerer'],  saveProficiencies: ['CON', 'CHA'], level1Features: DND5E_CLASS_FEATURES['sorcerer'] },
    { id: 'warlock',   name: 'Warlock',   emoji: '🌑', description: 'Pact-bound spellcaster empowered by an otherworldly patron.', hitDie: DND5E_HIT_DICE['warlock'], saveProficiencies: ['WIS', 'CHA'], level1Features: DND5E_CLASS_FEATURES['warlock'] },
    { id: 'wizard',    name: 'Wizard',    emoji: '📚', description: 'Master of arcane scholarship and prepared spellcasting.', hitDie: DND5E_HIT_DICE['wizard'], saveProficiencies: ['INT', 'WIS'], level1Features: DND5E_CLASS_FEATURES['wizard'] },
  ],
  backgroundLabel: 'Background',
  backgroundQuiz: [
    {
      id: 'q1',
      prompt: 'Before your life of adventure, you spent your days…',
      options: [
        { id: 'a', text: 'In a temple, monastery, or religious institution', scores: { acolyte: 3 } },
        { id: 'b', text: 'Running schemes, picking pockets, or working in the shadows', scores: { criminal: 3 } },
        { id: 'c', text: 'Working the land, sailing the seas, or roaming wild places', scores: { outlander: 2, folk_hero: 1 } },
        { id: 'd', text: 'Poring over ancient tomes and researching lore', scores: { sage: 3 } },
        { id: 'e', text: 'Learning a trade or craft within a guild', scores: { guild_artisan: 3 } },
      ],
    },
    {
      id: 'q2',
      prompt: 'The most valuable thing you carry is…',
      options: [
        { id: 'a', text: 'A holy symbol or sacred text', scores: { acolyte: 2, hermit: 1 } },
        { id: 'b', text: 'Lockpicks, forged papers, or a set of loaded dice', scores: { criminal: 2, charlatan: 1 } },
        { id: 'c', text: 'A memento from people who believe in you', scores: { folk_hero: 3 } },
        { id: 'd', text: 'A hunting trophy or hand-drawn wilderness map', scores: { outlander: 3 } },
        { id: 'e', text: 'A research journal or letter from a fellow scholar', scores: { sage: 2, hermit: 1 } },
      ],
    },
    {
      id: 'q3',
      prompt: 'When trouble finds your party, you are most likely to…',
      options: [
        { id: 'a', text: 'Mediate with calm spiritual authority', scores: { acolyte: 2, hermit: 1 } },
        { id: 'b', text: 'Look for the angle — everyone has a price', scores: { criminal: 2, charlatan: 1 } },
        { id: 'c', text: 'Stand your ground and protect the vulnerable', scores: { folk_hero: 2, soldier: 1 } },
        { id: 'd', text: 'Invoke your connections or social standing', scores: { noble: 3 } },
        { id: 'e', text: 'Prefer to observe from a distance before acting', scores: { hermit: 2, sage: 1 } },
      ],
    },
    {
      id: 'q4',
      prompt: 'People who know you would best describe you as…',
      options: [
        { id: 'a', text: 'Devout and principled — led by faith or a strict moral code', scores: { acolyte: 2, soldier: 1 } },
        { id: 'b', text: 'Cunning and adaptable — rules are suggestions, not laws', scores: { criminal: 2, charlatan: 1 } },
        { id: 'c', text: 'Scholarly and curious — always asking "why" or "how"', scores: { sage: 2, hermit: 1 } },
        { id: 'd', text: 'Earthy and dependable — do the work, earn the trust', scores: { folk_hero: 2, guild_artisan: 1 } },
        { id: 'e', text: 'Polished and well-connected — comfortable in any social circle', scores: { noble: 3 } },
      ],
    },
    {
      id: 'q5',
      prompt: 'Above all else, you venture into danger because you want to…',
      options: [
        { id: 'a', text: 'Fulfill a higher calling or atone for a past wrong', scores: { acolyte: 2, hermit: 1 } },
        { id: 'b', text: 'Accumulate wealth, power — or both', scores: { criminal: 1, noble: 2, charlatan: 1 } },
        { id: 'c', text: 'Protect those who cannot protect themselves', scores: { folk_hero: 3 } },
        { id: 'd', text: 'Uncover hidden truths and ancient secrets', scores: { sage: 2, hermit: 1, outlander: 1 } },
        { id: 'e', text: 'Forge a legend through blood, steel, and glory', scores: { soldier: 2, outlander: 1 } },
      ],
    },
  ],
  backgrounds: [
    {
      id: 'acolyte',
      name: 'Acolyte',
      description: 'Temple servant devoted to a higher power.',
      suggestedSkills: ['insight', 'religion'],
      flavorGear: ['Holy symbol', 'Prayer book', 'Vestments', 'Incense & censer'],
    },
    {
      id: 'criminal',
      name: 'Criminal',
      description: 'Skilled in shadows, surviving by wit and cunning.',
      suggestedSkills: ['deception', 'stealth'],
      flavorGear: ['Crowbar', 'Dark common clothes with hood', 'Lockpicks', 'Dice set'],
    },
    {
      id: 'charlatan',
      name: 'Charlatan',
      description: 'Silver-tongued con artist with a hundred false identities.',
      suggestedSkills: ['deception', 'sleight of hand'],
      flavorGear: ['Fine clothes', 'Disguise kit', 'Forged documents', 'Weighted dice'],
    },
    {
      id: 'folk_hero',
      name: 'Folk Hero',
      description: 'Champion of the common people — they believe in you.',
      suggestedSkills: ['animal handling', 'survival'],
      flavorGear: ["Craftsman's tools", 'Iron pot', 'Shovel', 'Set of common clothes'],
    },
    {
      id: 'guild_artisan',
      name: 'Guild Artisan',
      description: 'Trained craftsperson and valued guild member.',
      suggestedSkills: ['insight', 'persuasion'],
      flavorGear: ["Artisan's tools", 'Letter of introduction from guild', 'Traveler\'s clothes'],
    },
    {
      id: 'hermit',
      name: 'Hermit',
      description: 'Solitary seeker of hidden truths.',
      suggestedSkills: ['medicine', 'religion'],
      flavorGear: ['Scroll case with notes', 'Winter blanket', 'Herbalism kit', 'Small knife'],
    },
    {
      id: 'noble',
      name: 'Noble',
      description: 'Born to privilege and positioned for influence.',
      suggestedSkills: ['history', 'persuasion'],
      flavorGear: ['Signet ring', 'Scroll of pedigree', 'Fine clothes', 'Purse of gold'],
    },
    {
      id: 'outlander',
      name: 'Outlander',
      description: 'Survivor of the untamed wilds.',
      suggestedSkills: ['athletics', 'survival'],
      flavorGear: ['Staff', 'Hunting trap', 'Creature trophy', 'Traveler\'s clothes'],
    },
    {
      id: 'sage',
      name: 'Sage',
      description: 'Scholar and researcher of ancient lore.',
      suggestedSkills: ['arcana', 'history'],
      flavorGear: ['Ink & quill', 'Small knife', 'Letter from colleague', 'Common clothes'],
    },
    {
      id: 'soldier',
      name: 'Soldier',
      description: 'Veteran warrior with military discipline.',
      suggestedSkills: ['athletics', 'intimidation'],
      flavorGear: ['Rank insignia', 'Trophy from fallen enemy', 'Dice set', 'Common clothes'],
    },
  ],
  personalityFormat: 'dnd',
  skills: [
    { id: 'acrobatics', name: 'Acrobatics', stat: 'DEX' },
    { id: 'animal handling', name: 'Animal Handling', stat: 'WIS' },
    { id: 'arcana', name: 'Arcana', stat: 'INT' },
    { id: 'athletics', name: 'Athletics', stat: 'STR' },
    { id: 'deception', name: 'Deception', stat: 'CHA' },
    { id: 'history', name: 'History', stat: 'INT' },
    { id: 'insight', name: 'Insight', stat: 'WIS' },
    { id: 'intimidation', name: 'Intimidation', stat: 'CHA' },
    { id: 'investigation', name: 'Investigation', stat: 'INT' },
    { id: 'medicine', name: 'Medicine', stat: 'WIS' },
    { id: 'nature', name: 'Nature', stat: 'INT' },
    { id: 'perception', name: 'Perception', stat: 'WIS' },
    { id: 'performance', name: 'Performance', stat: 'CHA' },
    { id: 'persuasion', name: 'Persuasion', stat: 'CHA' },
    { id: 'religion', name: 'Religion', stat: 'INT' },
    { id: 'sleight of hand', name: 'Sleight of Hand', stat: 'DEX' },
    { id: 'stealth', name: 'Stealth', stat: 'DEX' },
    { id: 'survival', name: 'Survival', stat: 'WIS' },
  ],
  skillCount: 4,
  gearPackages: [
    { id: 'dungeoneer', name: "Dungeoneer's Pack", items: ['Backpack', 'Crowbar', 'Hammer & 10 pitons', 'Torches ×10', 'Tinderbox', 'Rations ×10', 'Waterskin', '50 ft hempen rope'] },
    { id: 'explorer', name: "Explorer's Pack", items: ['Backpack', 'Bedroll', 'Mess kit', 'Tinderbox', 'Torches ×10', 'Rations ×10', 'Waterskin', '50 ft hempen rope'] },
    { id: 'scholar', name: "Scholar's Pack", items: ['Backpack', 'Book of lore', 'Ink & quill', 'Parchment ×10', 'Small knife', 'Bag of sand', 'Candles ×10'] },
  ],
  levelRange: [1, 20],
  abilityScoreMethod: 'standard_array',
  availableLanguages: [
    'Common', 'Dwarvish', 'Elvish', 'Giant', 'Gnomish', 'Goblin',
    'Halfling', 'Orc', 'Abyssal', 'Celestial', 'Draconic',
    'Deep Speech', 'Infernal', 'Primordial', 'Sylvan', 'Undercommon',
  ],
  languageCount: 2,
  feats: DND5E_FEATS,
  featCountOnCreate: 1,
  availableSpells: DND5E_SPELLS,
  spellCountOnCreate: 4,
}

// ─────────────────────────────────────────────
// Pathfinder 2e
// ─────────────────────────────────────────────

const PF2E: WizardSystem = {
  id: 'pf2e',
  name: 'Pathfinder 2e',
  emoji: '🗺️',
  genre: 'Tactical Fantasy',
  blurb: 'Three-action economy, proficiency ranks, and deep build customization.',
  ancestryLabel: 'Ancestry',
  ancestries: [
    { id: 'human', name: 'Human', emoji: '🧑', description: 'Versatile with a free ancestry feat and extra skill.' },
    { id: 'elf', name: 'Elf', emoji: '🧝', description: 'Long-lived with low-light vision and natural arcane talent.' },
    { id: 'dwarf', name: 'Dwarf', emoji: '⛏️', description: 'Resilient and stubborn — darkvision and stonecunning.' },
    { id: 'gnome', name: 'Gnome', emoji: '🔮', description: 'Whimsical and small — low-light vision and fey-touched magic.' },
    { id: 'goblin', name: 'Goblin', emoji: '🔥', description: 'Chaotic and scrappy with darkvision and fire affinity.' },
    { id: 'halfling', name: 'Halfling', emoji: '🌿', description: 'Keen senses, natural luck, and a talent for blending in.' },
    { id: 'leshy', name: 'Leshy', emoji: '🍃', description: 'Plant-spirit animated by nature\'s power.' },
    { id: 'catfolk', name: 'Catfolk', emoji: '🐱', description: 'Agile wanderers with low-light vision and cat-fall.' },
    { id: 'tengu', name: 'Tengu', emoji: '🐦', description: 'Sharp-taloned bird-folk with weapon finesse and keen eyes.' },
    { id: 'other', name: 'Other / Rare', emoji: '✨', description: 'Kobold, Lizardfolk, Orc, Fetchling, and more.' },
  ],
  classLabel: 'Class',
  classes: [
    { id: 'alchemist', name: 'Alchemist', emoji: '⚗️', description: 'Explosive inventor with bombs and elixirs.' },
    { id: 'barbarian', name: 'Barbarian', emoji: '🪓', description: 'Rage-fueled warrior with powerful instincts.' },
    { id: 'bard', name: 'Bard', emoji: '🎵', description: 'Occult performer who inspires allies and debuffs foes.' },
    { id: 'champion', name: 'Champion', emoji: '⚜️', description: 'Divine warrior bound to a cause and a code.' },
    { id: 'cleric', name: 'Cleric', emoji: '✝️', description: 'Font of divine power — healer or damage dealer.' },
    { id: 'druid', name: 'Druid', emoji: '🌿', description: 'Nature caster with wild shape and primal magic.' },
    { id: 'fighter', name: 'Fighter', emoji: '🛡️', description: 'Precision combat master with the widest weapon access.' },
    { id: 'monk', name: 'Monk', emoji: '👊', description: 'Disciplined martial artist with ki abilities.' },
    { id: 'ranger', name: 'Ranger', emoji: '🏹', description: 'Hunter and tracker — mark your prey and pursue.' },
    { id: 'rogue', name: 'Rogue', emoji: '🗡️', description: 'Sneak attacker and skill powerhouse.' },
    { id: 'sorcerer', name: 'Sorcerer', emoji: '✨', description: 'Bloodline-fueled caster with flexible spell repertoire.' },
    { id: 'wizard', name: 'Wizard', emoji: '📚', description: 'Prepared arcane spellcaster with a thesis specialty.' },
    { id: 'witch', name: 'Witch', emoji: '🧙', description: 'Patron-bound caster with hexes and a familiar.' },
    { id: 'investigator', name: 'Investigator', emoji: '🔍', description: 'Tactical analyst who devises strategies on the fly.' },
  ],
  backgroundLabel: 'Background',
  backgroundQuiz: [
    {
      id: 'q1',
      prompt: 'Before adventuring, your life revolved around…',
      options: [
        { id: 'a', text: 'Faith, ritual, and service to a deity', scores: { acolyte: 3 } },
        { id: 'b', text: 'Illicit work — theft, smuggling, or information brokering', scores: { criminal: 3 } },
        { id: 'c', text: 'Academic study and magical or historical research', scores: { scholar: 3 } },
        { id: 'd', text: 'The frontier — survival, scouting, and wilderness travel', scores: { hunter: 2, nomad: 1 } },
        { id: 'e', text: 'A trade, guild, or artisanal craft', scores: { artisan: 3 } },
      ],
    },
    {
      id: 'q2',
      prompt: 'Your greatest strength is…',
      options: [
        { id: 'a', text: 'Spiritual resolve and knowledge of the divine', scores: { acolyte: 2, herbalist: 1 } },
        { id: 'b', text: 'An eye for weakness and an escape plan', scores: { criminal: 2, gambler: 1 } },
        { id: 'c', text: 'Understanding what others miss in plain sight', scores: { scholar: 2, detective: 1 } },
        { id: 'd', text: 'Moving unseen through any terrain', scores: { hunter: 2, nomad: 1 } },
        { id: 'e', text: 'Making things that last', scores: { artisan: 3 } },
      ],
    },
  ],
  backgrounds: [
    { id: 'acolyte', name: 'Acolyte', description: 'Temple initiate with divine knowledge.', suggestedSkills: ['religion', 'diplomacy'], flavorGear: ['Holy symbol', 'Prayer vestments', 'Incense'] },
    { id: 'criminal', name: 'Criminal', description: 'Underworld operative with street smarts.', suggestedSkills: ['thievery', 'stealth'], flavorGear: ['Thieves\' tools', 'Dark clothing'] },
    { id: 'scholar', name: 'Scholar', description: 'Academic researcher with broad knowledge.', suggestedSkills: ['arcana', 'society'], flavorGear: ['Research notes', 'Ink & quill', 'Reference text'] },
    { id: 'hunter', name: 'Hunter', description: 'Wilderness tracker and hunter.', suggestedSkills: ['nature', 'survival'], flavorGear: ['Hunting trap', 'Skinning knife', 'Rations'] },
    { id: 'artisan', name: 'Artisan', description: 'Skilled craftsperson from a respected trade.', suggestedSkills: ['crafting', 'diplomacy'], flavorGear: ["Artisan's tools", 'Guild letter'] },
    { id: 'nomad', name: 'Nomad', description: 'Wanderer with no fixed home.', suggestedSkills: ['survival', 'athletics'], flavorGear: ['Weathered pack', 'Route map', 'Bedroll'] },
    { id: 'gambler', name: 'Gambler', description: 'Risk-taker who lives on luck and nerve.', suggestedSkills: ['deception', 'society'], flavorGear: ['Dice set', 'Cards', 'Coin purse'] },
    { id: 'detective', name: 'Detective', description: 'Keen observer who unravels mysteries.', suggestedSkills: ['investigation', 'society'], flavorGear: ['Magnifying glass', 'Case notes'] },
    { id: 'herbalist', name: 'Herbalist', description: 'Healer who knows plants and poultices.', suggestedSkills: ['medicine', 'nature'], flavorGear: ['Herbalism kit', 'Poultice supplies'] },
  ],
  personalityFormat: 'dnd',
  skills: [
    { id: 'acrobatics', name: 'Acrobatics', stat: 'DEX' },
    { id: 'arcana', name: 'Arcana', stat: 'INT' },
    { id: 'athletics', name: 'Athletics', stat: 'STR' },
    { id: 'crafting', name: 'Crafting', stat: 'INT' },
    { id: 'deception', name: 'Deception', stat: 'CHA' },
    { id: 'diplomacy', name: 'Diplomacy', stat: 'CHA' },
    { id: 'intimidation', name: 'Intimidation', stat: 'CHA' },
    { id: 'medicine', name: 'Medicine', stat: 'WIS' },
    { id: 'nature', name: 'Nature', stat: 'WIS' },
    { id: 'occultism', name: 'Occultism', stat: 'INT' },
    { id: 'performance', name: 'Performance', stat: 'CHA' },
    { id: 'religion', name: 'Religion', stat: 'WIS' },
    { id: 'society', name: 'Society', stat: 'INT' },
    { id: 'stealth', name: 'Stealth', stat: 'DEX' },
    { id: 'survival', name: 'Survival', stat: 'WIS' },
    { id: 'thievery', name: 'Thievery', stat: 'DEX' },
    { id: 'investigation', name: 'Lore (Investigation)', stat: 'INT' },
  ],
  skillCount: 4,
  gearPackages: [
    { id: 'adventurer', name: "Adventurer's Pack", items: ['Backpack', 'Bedroll', 'Torches ×5', 'Rations ×5', 'Waterskin', 'Rope (50 ft)', 'Flint & steel'] },
    { id: 'scholar', name: "Scholar's Satchel", items: ['Satchel', 'Reference text', 'Ink & quill', 'Parchment ×10', 'Candles ×5'] },
  ],
  levelRange: [1, 20],
}

// ─────────────────────────────────────────────
// Pathfinder 1e
// ─────────────────────────────────────────────

const PF1E: WizardSystem = {
  id: 'pf1e',
  name: 'Pathfinder 1e',
  emoji: '🐉',
  genre: 'Heroic Fantasy (Classic)',
  blurb: 'D20 with base attack bonus, feat chains, and expansive class options.',
  ancestryLabel: 'Race',
  ancestries: [
    { id: 'human', name: 'Human', emoji: '🧑', description: 'Extra feat and skill rank per level — extremely versatile.' },
    { id: 'elf', name: 'Elf', emoji: '🧝', description: 'INT/DEX bonuses, low-light vision, and spell resistance.' },
    { id: 'dwarf', name: 'Dwarf', emoji: '⛏️', description: 'Darkvision, stonecunning, and deep racial enmity.' },
    { id: 'halfling', name: 'Halfling', emoji: '🌿', description: 'Fearless morale and a +1 to all saving throws.' },
    { id: 'gnome', name: 'Gnome', emoji: '🔮', description: 'Obsessive, small, and full of innate spell-like abilities.' },
    { id: 'half-elf', name: 'Half-Elf', emoji: '🌓', description: 'Elven immunities and a choice of racial favored class.' },
    { id: 'half-orc', name: 'Half-Orc', emoji: '💪', description: 'Darkvision and ferocity — won\'t drop until deeply wounded.' },
    { id: 'other', name: 'Other / Uncommon', emoji: '✨', description: 'Aasimar, Tiefling, Fetchling, and more from supplements.' },
  ],
  classLabel: 'Class',
  classes: [
    { id: 'alchemist', name: 'Alchemist', emoji: '⚗️', description: 'Bombs, mutagens, and extracts.' },
    { id: 'barbarian', name: 'Barbarian', emoji: '🪓', description: 'Rage-powered front-liner.' },
    { id: 'bard', name: 'Bard', emoji: '🎵', description: 'Perform-based buffing and versatile arcane magic.' },
    { id: 'cleric', name: 'Cleric', emoji: '✝️', description: 'Domain powers, channeling, and divine spells.' },
    { id: 'druid', name: 'Druid', emoji: '🌿', description: 'Wild shape and nature magic.' },
    { id: 'fighter', name: 'Fighter', emoji: '🛡️', description: 'Bonus feats and weapon training.' },
    { id: 'monk', name: 'Monk', emoji: '👊', description: 'Unarmed strikes and ki pool.' },
    { id: 'paladin', name: 'Paladin', emoji: '⚜️', description: 'Divine grace and smite evil.' },
    { id: 'ranger', name: 'Ranger', emoji: '🏹', description: 'Favored enemy and companion.' },
    { id: 'rogue', name: 'Rogue', emoji: '🗡️', description: 'Sneak attack, trapfinding, and rogue talents.' },
    { id: 'sorcerer', name: 'Sorcerer', emoji: '✨', description: 'Bloodline magic and spontaneous casting.' },
    { id: 'witch', name: 'Witch', emoji: '🧙', description: 'Hexes and patron-themed spells.' },
    { id: 'wizard', name: 'Wizard', emoji: '📚', description: 'Arcane school specialist with a spellbook.' },
    { id: 'oracle', name: 'Oracle', emoji: '🌙', description: 'Divine mystery with a mystery and a curse.' },
    { id: 'inquisitor', name: 'Inquisitor', emoji: '⚖️', description: 'Solo hunter of the divine — teamwork feats and bane.' },
  ],
  backgroundLabel: 'Trait / Background',
  backgroundQuiz: [
    {
      id: 'q1',
      prompt: 'What drove you to adventure first?',
      options: [
        { id: 'a', text: 'Faith called me to prove my devotion', scores: { devout: 3 } },
        { id: 'b', text: 'Necessity — poverty, exile, or survival', scores: { vagabond: 3 } },
        { id: 'c', text: 'The lure of knowledge I couldn\'t find at home', scores: { scholar: 3 } },
        { id: 'd', text: 'Personal honor — a debt or a quest', scores: { noble: 2, soldier: 1 } },
      ],
    },
  ],
  backgrounds: [
    { id: 'devout', name: 'Devout', description: 'Bound to faith and divine service.', suggestedSkills: ['knowledge religion', 'heal'], flavorGear: ['Holy symbol', 'Prayer beads'] },
    { id: 'vagabond', name: 'Vagabond', description: 'Survivor living on wit and movement.', suggestedSkills: ['survival', 'stealth'], flavorGear: ['Bedroll', 'Road rations'] },
    { id: 'scholar', name: 'Scholar', description: 'Student of lore and arcane secrets.', suggestedSkills: ['knowledge arcana', 'spellcraft'], flavorGear: ['Research notes', 'Writing kit'] },
    { id: 'noble', name: 'Noble Scion', description: 'Born of rank with something to prove.', suggestedSkills: ['knowledge nobility', 'diplomacy'], flavorGear: ['Signet ring', 'Fine clothes'] },
    { id: 'soldier', name: 'Soldier', description: 'Veteran of a war or militia.', suggestedSkills: ['intimidate', 'perception'], flavorGear: ['Military insignia', 'Rations'] },
  ],
  personalityFormat: 'simple',
  skills: [
    { id: 'acrobatics', name: 'Acrobatics' }, { id: 'appraise', name: 'Appraise' },
    { id: 'bluff', name: 'Bluff' }, { id: 'climb', name: 'Climb' },
    { id: 'diplomacy', name: 'Diplomacy' }, { id: 'disable device', name: 'Disable Device' },
    { id: 'disguise', name: 'Disguise' }, { id: 'escape artist', name: 'Escape Artist' },
    { id: 'fly', name: 'Fly' }, { id: 'handle animal', name: 'Handle Animal' },
    { id: 'heal', name: 'Heal' }, { id: 'intimidate', name: 'Intimidate' },
    { id: 'knowledge arcana', name: 'Knowledge (Arcana)' }, { id: 'knowledge nature', name: 'Knowledge (Nature)' },
    { id: 'knowledge religion', name: 'Knowledge (Religion)' }, { id: 'perception', name: 'Perception' },
    { id: 'ride', name: 'Ride' }, { id: 'sense motive', name: 'Sense Motive' },
    { id: 'spellcraft', name: 'Spellcraft' }, { id: 'stealth', name: 'Stealth' },
    { id: 'survival', name: 'Survival' }, { id: 'swim', name: 'Swim' },
    { id: 'use magic device', name: 'Use Magic Device' },
  ],
  skillCount: 4,
  gearPackages: [
    { id: 'standard', name: 'Standard Adventurer', items: ['Backpack', 'Bedroll', 'Flint & steel', 'Torches ×5', 'Rations ×5', 'Rope 50 ft'] },
  ],
  levelRange: [1, 20],
}

// ─────────────────────────────────────────────
// Starfinder
// ─────────────────────────────────────────────

const STARFINDER: WizardSystem = {
  id: 'starfinder',
  name: 'Starfinder',
  emoji: '🚀',
  genre: 'Science Fantasy',
  blurb: 'Space opera meets high fantasy — starships, magic, and alien worlds.',
  ancestryLabel: 'Race',
  ancestries: [
    { id: 'android', name: 'Android', emoji: '🤖', description: 'Synthetic humanoid with logical precision and immunity to disease.' },
    { id: 'human', name: 'Human', emoji: '🧑', description: 'Adaptable and driven — bonus feat and skill rank.' },
    { id: 'lashunta', name: 'Lashunta', emoji: '🧠', description: 'Dimorphic telepaths with innate spell-like abilities.' },
    { id: 'shirren', name: 'Shirren', emoji: '🦗', description: 'Insectoid hive-mind refugees with blindsense.' },
    { id: 'vesk', name: 'Vesk', emoji: '🦎', description: 'Reptilian warriors with natural weapons and armor.' },
    { id: 'ysoki', name: 'Ysoki', emoji: '🐀', description: 'Rat-folk engineers with cheek pouches and moxie.' },
    { id: 'kasatha', name: 'Kasatha', emoji: '🙌', description: 'Four-armed desert wanderers with desert runner and historian traits.' },
    { id: 'other', name: 'Other Species', emoji: '👽', description: 'Contemplative, Draelik, Kalo, Pahtra, and more.' },
  ],
  classLabel: 'Class',
  classes: [
    { id: 'envoy', name: 'Envoy', emoji: '🗣️', description: 'Face and field commander — improvisations buff allies.' },
    { id: 'mechanic', name: 'Mechanic', emoji: '🔧', description: 'Tech specialist with an AI or drone partner.' },
    { id: 'mystic', name: 'Mystic', emoji: '🔮', description: 'Spellcaster connected to the Drift and cosmic mysteries.' },
    { id: 'operative', name: 'Operative', emoji: '🗡️', description: 'Skill-based specialist with trick attack and a specialization.' },
    { id: 'solarian', name: 'Solarian', emoji: '☀️', description: 'Star-attuned warrior channeling photon and graviton modes.' },
    { id: 'soldier', name: 'Soldier', emoji: '🪖', description: 'Combat powerhouse with a fighting style and gear boosts.' },
    { id: 'technomancer', name: 'Technomancer', emoji: '💻', description: 'Magic-meets-tech spellcaster — hacks and hexes combined.' },
    { id: 'biohacker', name: 'Biohacker', emoji: '🧬', description: 'Scientist who injects buffs and debuffs mid-combat.' },
    { id: 'witchwarper', name: 'Witchwarper', emoji: '🌀', description: 'Multiverse-attuned caster who bends reality on the fly.' },
  ],
  backgroundLabel: 'Theme',
  backgroundQuiz: [
    {
      id: 'q1',
      prompt: 'What drew you to a life among the stars?',
      options: [
        { id: 'a', text: 'Military service or a cause worth fighting for', scores: { mercenary: 3 } },
        { id: 'b', text: 'The lure of undiscovered worlds and alien life', scores: { xenoseeker: 3 } },
        { id: 'c', text: 'A corporation offered credits and resources', scores: { corporate_agent: 3 } },
        { id: 'd', text: 'Pure scholarly curiosity about the cosmos', scores: { scholar: 3 } },
        { id: 'e', text: 'Something happened that left me with no other choice', scores: { outlaw: 3 } },
      ],
    },
  ],
  backgrounds: [
    { id: 'mercenary', name: 'Mercenary', description: 'Soldier for hire.', suggestedSkills: ['athletics', 'intimidate'], flavorGear: ['Combat knife', 'Standard issue armor'] },
    { id: 'xenoseeker', name: 'Xenoseeker', description: 'Explorer of alien life.', suggestedSkills: ['life science', 'culture'], flavorGear: ['Field scanner', 'Sample containers'] },
    { id: 'corporate_agent', name: 'Corporate Agent', description: 'Working for a megacorp.', suggestedSkills: ['computers', 'diplomacy'], flavorGear: ['Encrypted comm', 'Corporate ID'] },
    { id: 'scholar', name: 'Scholar', description: 'Academic researcher.', suggestedSkills: ['physical science', 'life science'], flavorGear: ['Research tablet', 'Lab kit'] },
    { id: 'outlaw', name: 'Outlaw', description: 'On the run from the law.', suggestedSkills: ['stealth', 'sleight of hand'], flavorGear: ['Fake ID', 'Contraband pack'] },
  ],
  personalityFormat: 'simple',
  skills: [
    { id: 'acrobatics', name: 'Acrobatics' }, { id: 'athletics', name: 'Athletics' },
    { id: 'bluff', name: 'Bluff' }, { id: 'computers', name: 'Computers' },
    { id: 'culture', name: 'Culture' }, { id: 'diplomacy', name: 'Diplomacy' },
    { id: 'disguise', name: 'Disguise' }, { id: 'engineering', name: 'Engineering' },
    { id: 'intimidate', name: 'Intimidate' }, { id: 'life science', name: 'Life Science' },
    { id: 'medicine', name: 'Medicine' }, { id: 'mysticism', name: 'Mysticism' },
    { id: 'perception', name: 'Perception' }, { id: 'physical science', name: 'Physical Science' },
    { id: 'piloting', name: 'Piloting' }, { id: 'sense motive', name: 'Sense Motive' },
    { id: 'sleight of hand', name: 'Sleight of Hand' }, { id: 'stealth', name: 'Stealth' },
    { id: 'survival', name: 'Survival' },
  ],
  skillCount: 5,
  gearPackages: [
    { id: 'field', name: 'Field Kit', items: ['Backpack', 'Comm unit', 'First aid kit', 'Rations ×3', 'Flashlight', 'Credstick (100 credits)'] },
  ],
  levelRange: [1, 20],
}

// ─────────────────────────────────────────────
// Call of Cthulhu
// ─────────────────────────────────────────────

const COC: WizardSystem = {
  id: 'coc',
  name: 'Call of Cthulhu',
  emoji: '🐙',
  genre: 'Cosmic Horror',
  blurb: 'Percentile-based horror investigation set in the 1920s (or adaptable eras).',
  ancestryLabel: null, // All human
  ancestries: null,
  classLabel: 'Occupation',
  classes: [
    { id: 'archaeologist', name: 'Archaeologist', emoji: '🏺', description: 'Expert in ancient sites, artifacts, and languages.' },
    { id: 'detective', name: 'Detective', emoji: '🔍', description: 'Sharp investigator who follows the evidence.' },
    { id: 'doctor', name: 'Doctor / Physician', emoji: '⚕️', description: 'Medical professional with biological knowledge.' },
    { id: 'journalist', name: 'Journalist', emoji: '📰', description: 'Nose for news — and for trouble.' },
    { id: 'professor', name: 'Professor', emoji: '🎓', description: 'Academic authority with broad knowledge.' },
    { id: 'dilettante', name: 'Dilettante', emoji: '🎩', description: 'Wealthy socialite with unexpected resources.' },
    { id: 'soldier', name: 'Soldier / Veteran', emoji: '🪖', description: 'Combat-hardened survivor of war.' },
    { id: 'occultist', name: 'Occultist', emoji: '🔮', description: 'Seeker of forbidden lore — knows just enough to be dangerous.' },
    { id: 'nurse', name: 'Nurse / Field Medic', emoji: '🩺', description: 'Practical healer under pressure.' },
    { id: 'author', name: 'Author / Artist', emoji: '✍️', description: 'Creative with a keen eye and a way with words.' },
  ],
  backgroundLabel: 'Personal Story',
  backgroundQuiz: [
    {
      id: 'q1',
      prompt: 'What first led you to take on this investigation?',
      options: [
        { id: 'a', text: 'A friend or colleague disappeared without explanation', scores: { personal_loss: 3 } },
        { id: 'b', text: 'I was hired — it\'s simply the job', scores: { professional: 3 } },
        { id: 'c', text: 'Academic curiosity about unexplained phenomena', scores: { academic: 3 } },
        { id: 'd', text: 'I stumbled into it and now I can\'t walk away', scores: { reluctant: 3 } },
      ],
    },
  ],
  backgrounds: [
    { id: 'personal_loss', name: 'Personal Stakes', description: 'Someone you cared about is gone.', suggestedSkills: ['psychology', 'track'], flavorGear: ['Personal photo', 'Old letters'] },
    { id: 'professional', name: 'Professional', description: 'This is what you do for a living.', suggestedSkills: ['persuade', 'spot hidden'], flavorGear: ['Business card', 'Case files'] },
    { id: 'academic', name: 'Academic Pursuer', description: 'The puzzle is too fascinating to ignore.', suggestedSkills: ['library use', 'cthulhu mythos'], flavorGear: ['Research journal', 'Reference books'] },
    { id: 'reluctant', name: 'Reluctant Investigator', description: 'Drawn in against your better judgment.', suggestedSkills: ['fast talk', 'dodge'], flavorGear: ['Improvised weapon', 'Emergency cash'] },
  ],
  personalityFormat: 'simple',
  skills: [
    { id: 'accounting', name: 'Accounting' }, { id: 'anthropology', name: 'Anthropology' },
    { id: 'archaeology', name: 'Archaeology' }, { id: 'art/craft', name: 'Art/Craft' },
    { id: 'charm', name: 'Charm' }, { id: 'climb', name: 'Climb' },
    { id: 'cthulhu mythos', name: 'Cthulhu Mythos' }, { id: 'disguise', name: 'Disguise' },
    { id: 'dodge', name: 'Dodge' }, { id: 'drive auto', name: 'Drive Auto' },
    { id: 'elec. repair', name: 'Elec. Repair' }, { id: 'fast talk', name: 'Fast Talk' },
    { id: 'firearms', name: 'Firearms' }, { id: 'first aid', name: 'First Aid' },
    { id: 'history', name: 'History' }, { id: 'intimidate', name: 'Intimidate' },
    { id: 'jump', name: 'Jump' }, { id: 'language (other)', name: 'Language (Other)' },
    { id: 'law', name: 'Law' }, { id: 'library use', name: 'Library Use' },
    { id: 'listen', name: 'Listen' }, { id: 'locksmith', name: 'Locksmith' },
    { id: 'medicine', name: 'Medicine' }, { id: 'navigate', name: 'Navigate' },
    { id: 'occult', name: 'Occult' }, { id: 'persuade', name: 'Persuade' },
    { id: 'photography', name: 'Photography' }, { id: 'psychology', name: 'Psychology' },
    { id: 'science', name: 'Science (choose)' }, { id: 'sleight of hand', name: 'Sleight of Hand' },
    { id: 'spot hidden', name: 'Spot Hidden' }, { id: 'stealth', name: 'Stealth' },
    { id: 'swim', name: 'Swim' }, { id: 'throw', name: 'Throw' },
    { id: 'track', name: 'Track' },
  ],
  skillCount: 6,
  gearPackages: [
    { id: 'investigator', name: 'Investigator Kit', items: ['Notebook & pen', 'Flashlight', 'Camera', 'First aid kit', 'Lighter', 'Lock picks'] },
    { id: 'academic', name: 'Academic Bag', items: ['Reference books', 'Research notes', 'Magnifying glass', 'Pen & ink', 'Maps'] },
  ],
  levelRange: null,
}

// ─────────────────────────────────────────────
// Star Trek Adventures
// ─────────────────────────────────────────────

const STARTREK: WizardSystem = {
  id: 'startrek',
  name: 'Star Trek Adventures',
  emoji: '🖖',
  genre: 'Science Fiction',
  blurb: '2d20 system focused on exploration, diplomacy, and Starfleet values.',
  ancestryLabel: 'Species',
  ancestries: [
    { id: 'human', name: 'Human', emoji: '🧑', description: 'Adaptable and driven — the heart of Starfleet.' },
    { id: 'vulcan', name: 'Vulcan', emoji: '🖖', description: 'Logical masters of intellect and emotional control.' },
    { id: 'andorian', name: 'Andorian', emoji: '🔵', description: 'Fiercely honorable warriors with antenna senses.' },
    { id: 'betazoid', name: 'Betazoid', emoji: '💜', description: 'Empaths and telepaths who understand all emotion.' },
    { id: 'bajoran', name: 'Bajoran', emoji: '🌀', description: 'Spiritual survivors with deep cultural resilience.' },
    { id: 'trill', name: 'Trill', emoji: '🌟', description: 'Joined symbionts carrying lifetimes of memory.' },
    { id: 'klingon', name: 'Klingon', emoji: '⚔️', description: 'Honor-bound warriors serving the Empire — or challenging it.' },
    { id: 'ferengi', name: 'Ferengi', emoji: '💰', description: 'Shrewd negotiators motivated by profit and rules of acquisition.' },
    { id: 'other', name: 'Other Species', emoji: '👽', description: 'Caitian, Denobulan, Tellarite, and many more.' },
  ],
  classLabel: 'Department',
  classes: [
    { id: 'command', name: 'Command', emoji: '🎖️', description: 'Leadership, tactics, and ship operations.' },
    { id: 'conn', name: 'Conn / Helm', emoji: '🕹️', description: 'Piloting, navigation, and vehicle control.' },
    { id: 'security', name: 'Security / Tactical', emoji: '🛡️', description: 'Combat, defense, and threat assessment.' },
    { id: 'engineering', name: 'Engineering', emoji: '🔧', description: 'Ship systems, repairs, and technical solutions.' },
    { id: 'science', name: 'Science', emoji: '🔭', description: 'Research, analysis, and sensor operations.' },
    { id: 'medicine', name: 'Medicine', emoji: '⚕️', description: 'Healing, biology, and counseling.' },
  ],
  backgroundLabel: 'Upbringing',
  backgroundQuiz: [
    {
      id: 'q1',
      prompt: 'Why did you join Starfleet?',
      options: [
        { id: 'a', text: 'To explore the unknown and make first contact', scores: { explorer: 3 } },
        { id: 'b', text: 'To protect the Federation and its people', scores: { defender: 3 } },
        { id: 'c', text: 'Because science is the key to understanding all things', scores: { scientist: 3 } },
        { id: 'd', text: 'Duty, honor, and service to a greater cause', scores: { dutiful: 3 } },
      ],
    },
  ],
  backgrounds: [
    { id: 'explorer', name: 'Explorer', description: 'Driven by curiosity about what lies beyond.', suggestedSkills: ['science', 'conn'], flavorGear: ['Tricorder', 'Field kit'] },
    { id: 'defender', name: 'Defender', description: 'Sworn to protect life and the Federation.', suggestedSkills: ['security', 'medicine'], flavorGear: ['Phaser', 'Combadge'] },
    { id: 'scientist', name: 'Scientist', description: 'Researcher seeking answers in the data.', suggestedSkills: ['science', 'engineering'], flavorGear: ['PADD', 'Research notes'] },
    { id: 'dutiful', name: 'Dutiful Officer', description: 'Mission first, always.', suggestedSkills: ['command', 'conn'], flavorGear: ['Duty roster', 'Rank insignia'] },
  ],
  personalityFormat: 'simple',
  skills: [
    { id: 'command', name: 'Command' }, { id: 'conn', name: 'Conn' },
    { id: 'security', name: 'Security' }, { id: 'engineering', name: 'Engineering' },
    { id: 'science', name: 'Science' }, { id: 'medicine', name: 'Medicine' },
  ],
  skillCount: 3,
  gearPackages: [
    { id: 'standard', name: 'Standard Loadout', items: ['Phaser pistol', 'Tricorder', 'Combadge', 'PADD', 'Emergency beacon'] },
  ],
  levelRange: [1, 5],
}

// ─────────────────────────────────────────────
// Shadow of the Demon Lord
// ─────────────────────────────────────────────

const SOTDL: WizardSystem = {
  id: 'sotdl',
  name: 'Shadow of the Demon Lord',
  emoji: '💀',
  genre: 'Dark Fantasy Horror',
  blurb: 'Fast, lethal, and dark — d20 resolution with master and expert path progression.',
  ancestryLabel: 'Ancestry',
  ancestries: [
    { id: 'human', name: 'Human', emoji: '🧑', description: 'Adaptable survivors in a dying world.' },
    { id: 'dwarf', name: 'Dwarf', emoji: '⛏️', description: 'Stone-hearted and stubborn, immune to being frightened.' },
    { id: 'goblin', name: 'Goblin', emoji: '🔥', description: 'Fast, small, and surprisingly clever.' },
    { id: 'changeling', name: 'Changeling', emoji: '🌘', description: 'Fey-born shapeshifter walking among mortals.' },
    { id: 'clockwork', name: 'Clockwork', emoji: '⚙️', description: 'Constructed being searching for purpose.' },
    { id: 'orc', name: 'Orc', emoji: '💪', description: 'Born of chaos — fierce and unpredictable.' },
  ],
  classLabel: 'Novice Path',
  classes: [
    { id: 'warrior', name: 'Warrior', emoji: '⚔️', description: 'Combat-hardened fighter with extra attack options.' },
    { id: 'rogue', name: 'Rogue', emoji: '🗡️', description: 'Cunning criminal with speed and dirty tricks.' },
    { id: 'priest', name: 'Priest', emoji: '✝️', description: 'Servant of a religion with divine magic.' },
    { id: 'magician', name: 'Magician', emoji: '📚', description: 'Student of the magical traditions.' },
  ],
  backgroundLabel: 'Background',
  backgroundQuiz: [
    {
      id: 'q1',
      prompt: 'What shaped you before the darkness came?',
      options: [
        { id: 'a', text: 'Warfare, guard service, or mercenary work', scores: { soldier: 3 } },
        { id: 'b', text: 'Life on the streets — theft, survival, crime', scores: { criminal: 3 } },
        { id: 'c', text: 'Service to a faith or secret society', scores: { devotee: 3 } },
        { id: 'd', text: 'Study of magic or forbidden lore', scores: { scholar: 3 } },
      ],
    },
  ],
  backgrounds: [
    { id: 'soldier', name: 'Soldier', description: 'Combat veteran.', suggestedSkills: ['athletics', 'intimidation'], flavorGear: ['Short sword', 'Leather armor'] },
    { id: 'criminal', name: 'Criminal', description: 'Thief and survivor.', suggestedSkills: ['stealth', 'trickery'], flavorGear: ['Dagger', 'Dark clothes'] },
    { id: 'devotee', name: 'Devotee', description: 'Faithful servant of a higher power.', suggestedSkills: ['religion', 'healing'], flavorGear: ['Holy symbol', 'Candles'] },
    { id: 'scholar', name: 'Scholar', description: 'Student of dark truths.', suggestedSkills: ['arcana', 'history'], flavorGear: ['Spellbook', 'Quill & ink'] },
  ],
  personalityFormat: 'simple',
  skills: [
    { id: 'athletics', name: 'Athletics' }, { id: 'arcana', name: 'Arcana' },
    { id: 'healing', name: 'Healing' }, { id: 'history', name: 'History' },
    { id: 'intimidation', name: 'Intimidation' }, { id: 'nature', name: 'Nature' },
    { id: 'perception', name: 'Perception' }, { id: 'religion', name: 'Religion' },
    { id: 'stealth', name: 'Stealth' }, { id: 'trickery', name: 'Trickery' },
  ],
  skillCount: 3,
  gearPackages: [
    { id: 'basic', name: 'Basic Survival Gear', items: ['Backpack', 'Torch ×3', 'Rations ×3', 'Rope 30 ft', 'Water skin'] },
  ],
  levelRange: [1, 10],
}

// ─────────────────────────────────────────────
// Warhammer Fantasy Roleplay (4e)
// ─────────────────────────────────────────────

const WFRP: WizardSystem = {
  id: 'wfrp',
  name: 'Warhammer Fantasy Roleplay',
  emoji: '🐺',
  genre: 'Grimdark Fantasy',
  blurb: 'Percentile system in the grim Old World — low power, high stakes, dark humor.',
  ancestryLabel: 'Species',
  ancestries: [
    { id: 'human', name: 'Human', emoji: '🧑', description: 'Dominant and varied — access to more careers than any other.' },
    { id: 'halfling', name: 'Halfling', emoji: '🌿', description: 'Short, lucky, and supernaturally good shots with a sling.' },
    { id: 'dwarf', name: 'Dwarf', emoji: '⛏️', description: 'Stubborn, grudge-bearing, and supernaturally tough.' },
    { id: 'high_elf', name: 'High Elf', emoji: '🧝', description: 'Arrogant, ancient, and magically gifted.' },
    { id: 'wood_elf', name: 'Wood Elf', emoji: '🏹', description: 'Forest-bound and rarely seen — deadly archers.' },
    { id: 'gnome', name: 'Gnome', emoji: '🔮', description: 'Rare and peculiar magical tinkerers.' },
  ],
  classLabel: 'Career',
  classes: [
    { id: 'soldier', name: 'Soldier', emoji: '⚔️', description: 'Empire military — regimented and battle-ready.' },
    { id: 'thief', name: 'Thief', emoji: '🗡️', description: 'Urbane criminal with a knack for disappearing.' },
    { id: 'witch_hunter', name: 'Witch Hunter', emoji: '🔥', description: 'Zealous enforcer of the Empire\'s laws against magic.' },
    { id: 'scholar', name: 'Scholar', emoji: '📚', description: 'Academic with broad and dangerous knowledge.' },
    { id: 'wizard', name: 'Wizard\'s Apprentice', emoji: '✨', description: 'Student of the Colleges of Magic.' },
    { id: 'priest', name: 'Initiate / Priest', emoji: '✝️', description: 'Servant of one of the Old World\'s gods.' },
    { id: 'ratcatcher', name: 'Ratcatcher', emoji: '🐀', description: 'Humble pest controller — surprisingly well-traveled.' },
    { id: 'innkeeper', name: 'Innkeeper', emoji: '🍺', description: 'Keeper of secrets and ale.' },
  ],
  backgroundLabel: 'Background & Motivation',
  backgroundQuiz: [
    {
      id: 'q1',
      prompt: 'What set you on the path to adventure?',
      options: [
        { id: 'a', text: 'The Empire called — conscription or duty', scores: { imperial: 3 } },
        { id: 'b', text: 'Poverty left me no choice but to seek fortune', scores: { commoner: 3 } },
        { id: 'c', text: 'Forbidden knowledge called — too loud to ignore', scores: { seeker: 3 } },
        { id: 'd', text: 'Chaos claimed something precious — now I hunt it', scores: { avenger: 3 } },
      ],
    },
  ],
  backgrounds: [
    { id: 'imperial', name: 'Imperial Servant', description: 'Bound to the Empire\'s needs.', suggestedSkills: ['melee', 'leadership'], flavorGear: ['Empire uniform', 'Sword'] },
    { id: 'commoner', name: 'Struggling Commoner', description: 'Born poor, still poor.', suggestedSkills: ['haggle', 'stealth'], flavorGear: ['Patched clothes', 'Knife'] },
    { id: 'seeker', name: 'Seeker of Truth', description: 'Knowledge is worth the risk.', suggestedSkills: ['lore', 'arcana'], flavorGear: ['Notebook', 'Candle'] },
    { id: 'avenger', name: 'Avenger', description: 'Chaos took something. Now you repay the debt.', suggestedSkills: ['perception', 'intimidate'], flavorGear: ['Weapon from the fallen', 'Grudge list'] },
  ],
  personalityFormat: 'simple',
  skills: [
    { id: 'athletics', name: 'Athletics' }, { id: 'bribery', name: 'Bribery' },
    { id: 'charm', name: 'Charm' }, { id: 'climb', name: 'Climb' },
    { id: 'cool', name: 'Cool' }, { id: 'dodge', name: 'Dodge' },
    { id: 'endurance', name: 'Endurance' }, { id: 'haggle', name: 'Haggle' },
    { id: 'intimidate', name: 'Intimidate' }, { id: 'intuition', name: 'Intuition' },
    { id: 'leadership', name: 'Leadership' }, { id: 'lore', name: 'Lore' },
    { id: 'melee', name: 'Melee' }, { id: 'navigation', name: 'Navigation' },
    { id: 'perception', name: 'Perception' }, { id: 'ranged', name: 'Ranged' },
    { id: 'ride', name: 'Ride' }, { id: 'row', name: 'Row' },
    { id: 'stealth', name: 'Stealth' }, { id: 'swim', name: 'Swim' },
  ],
  skillCount: 5,
  gearPackages: [
    { id: 'basic', name: 'Old World Traveler', items: ['Backpack', 'Blanket', 'Candles ×3', 'Tinderbox', 'Rations ×2', 'Water skin', 'Small knife'] },
  ],
  levelRange: null,
}

// ─────────────────────────────────────────────
// Alien RPG
// ─────────────────────────────────────────────

const ALIEN: WizardSystem = {
  id: 'alien',
  name: 'Alien RPG',
  emoji: '🎃',
  genre: 'Sci-Fi Horror',
  blurb: 'Year Zero Engine in the dark of space — stress dice make everything worse.',
  ancestryLabel: null,
  ancestries: null,
  classLabel: 'Career',
  classes: [
    { id: 'colonial_marine', name: 'Colonial Marine', emoji: '🪖', description: 'Front-line military grunt — tough but expendable.' },
    { id: 'company_agent', name: 'Company Agent', emoji: '💼', description: 'Weyland-Yutani operative — always has an agenda.' },
    { id: 'colonial_marshal', name: 'Colonial Marshal', emoji: '⚖️', description: 'Lawkeeper on the frontier with limited backup.' },
    { id: 'roughneck', name: 'Roughneck', emoji: '⛏️', description: 'Blue-collar worker who knows the machinery.' },
    { id: 'medic', name: 'Medic', emoji: '⚕️', description: 'Field healer who works under impossible conditions.' },
    { id: 'pilot', name: 'Pilot', emoji: '🚀', description: 'Spacecraft and dropship operator.' },
    { id: 'scientist', name: 'Scientist', emoji: '🔬', description: 'Researcher assigned to something best left undiscovered.' },
  ],
  backgroundLabel: 'Personal Agenda',
  backgroundQuiz: [
    {
      id: 'q1',
      prompt: 'Deep down, what matters most to you on this mission?',
      options: [
        { id: 'a', text: 'Getting out alive — nothing else matters', scores: { survivor: 3 } },
        { id: 'b', text: 'The mission succeeds, whatever the cost', scores: { company: 3 } },
        { id: 'c', text: 'The people around me come home', scores: { protector: 3 } },
        { id: 'd', text: 'The truth — whatever it is — gets out', scores: { truth_seeker: 3 } },
      ],
    },
  ],
  backgrounds: [
    { id: 'survivor', name: 'Survivor', description: 'Self-preservation above all.', suggestedSkills: ['survival', 'observation'], flavorGear: ['Emergency kit', 'Personal sidearm'] },
    { id: 'company', name: 'Company Loyalist', description: 'The mission is everything.', suggestedSkills: ['command', 'computers'], flavorGear: ['Encrypted datapad', 'Access codes'] },
    { id: 'protector', name: 'Protector', description: 'Lives are worth fighting for.', suggestedSkills: ['close combat', 'medical aid'], flavorGear: ['First aid kit', 'Combat armor'] },
    { id: 'truth_seeker', name: 'Truth Seeker', description: 'The cover-up ends here.', suggestedSkills: ['observation', 'comtech'], flavorGear: ['Recording device', 'Evidence bag'] },
  ],
  personalityFormat: 'simple',
  skills: [
    { id: 'close combat', name: 'Close Combat' }, { id: 'command', name: 'Command' },
    { id: 'comtech', name: 'Comtech' }, { id: 'heavy machinery', name: 'Heavy Machinery' },
    { id: 'manipulation', name: 'Manipulation' }, { id: 'medical aid', name: 'Medical Aid' },
    { id: 'mobility', name: 'Mobility' }, { id: 'observation', name: 'Observation' },
    { id: 'piloting', name: 'Piloting' }, { id: 'ranged combat', name: 'Ranged Combat' },
    { id: 'stamina', name: 'Stamina' }, { id: 'survival', name: 'Survival' },
  ],
  skillCount: 3,
  gearPackages: [
    { id: 'survival', name: 'Survival Pack', items: ['Emergency beacon', 'Oxygen mask', 'Rations ×3', 'Flashlight', 'First aid kit', 'Personal sidearm'] },
  ],
  levelRange: null,
}

// ─────────────────────────────────────────────
// Shadowrun
// ─────────────────────────────────────────────

const SHADOWRUN: WizardSystem = {
  id: 'shadowrun',
  name: 'Shadowrun',
  emoji: '🌆',
  genre: 'Cyberpunk Fantasy',
  blurb: 'Where the sprawl meets the Sixth World — dice pools, nuyen, and awakened magic.',
  ancestryLabel: 'Metatype',
  ancestries: [
    { id: 'human', name: 'Human', emoji: '🧑', description: 'Most common — bonus Karma at character creation.' },
    { id: 'elf', name: 'Elf', emoji: '🧝', description: 'Charismatic and perceptive — low-light vision.' },
    { id: 'dwarf', name: 'Dwarf', emoji: '⛏️', description: 'Thermographic vision, resistance to pathogens.' },
    { id: 'ork', name: 'Ork', emoji: '💪', description: 'Low-light vision, natural intimidation.' },
    { id: 'troll', name: 'Troll', emoji: '🧱', description: 'Thermographic vision, natural armor, and imposing size.' },
  ],
  classLabel: 'Archetype / Role',
  classes: [
    { id: 'street_samurai', name: 'Street Samurai', emoji: '🗡️', description: 'Cyber-enhanced close/ranged combat specialist.' },
    { id: 'decker', name: 'Decker', emoji: '💻', description: 'Matrix hacker who works in the virtual grid.' },
    { id: 'technomancer', name: 'Technomancer', emoji: '🌐', description: 'Resonance-attuned Matrix runner without hardware.' },
    { id: 'rigger', name: 'Rigger', emoji: '🚗', description: 'Vehicle and drone specialist with remote-control rigs.' },
    { id: 'face', name: 'Face', emoji: '🎩', description: 'Social expert — negotiation and deception are weapons.' },
    { id: 'mage', name: 'Mage', emoji: '✨', description: 'Awakened hermetic mage — spells and rituals.' },
    { id: 'shaman', name: 'Shaman', emoji: '🌿', description: 'Awakened spiritual caster — conjures spirits.' },
    { id: 'adept', name: 'Adept', emoji: '👊', description: 'Awakened physical warrior — body as the focus.' },
  ],
  backgroundLabel: 'Background',
  backgroundQuiz: [
    {
      id: 'q1',
      prompt: 'What pushed you into the shadows?',
      options: [
        { id: 'a', text: 'A corporation burned me — burned everything', scores: { corp_burnout: 3 } },
        { id: 'b', text: 'The sprawl raised me — this life is all I know', scores: { streetwise: 3 } },
        { id: 'c', text: 'I was recruited — the pay is too good to refuse', scores: { mercenary: 3 } },
        { id: 'd', text: 'Awakening changed me — magic demands answers', scores: { awakened: 3 } },
      ],
    },
  ],
  backgrounds: [
    { id: 'corp_burnout', name: 'Corp Burnout', description: 'Corporate life tried to consume you.', suggestedSkills: ['etiquette (corporate)', 'con'], flavorGear: ['Old corp badge', 'Burner commlink'] },
    { id: 'streetwise', name: 'Sprawl Survivor', description: 'The streets of the megacity are home.', suggestedSkills: ['streetwise', 'stealth'], flavorGear: ['Street clothes', 'Knife'] },
    { id: 'mercenary', name: 'Mercenary', description: 'Working for nuyen, no questions asked.', suggestedSkills: ['intimidation', 'firearms'], flavorGear: ['Holdout pistol', 'Armor jacket'] },
    { id: 'awakened', name: 'Newly Awakened', description: 'Magic arrived unbidden and changed everything.', suggestedSkills: ['spellcasting', 'arcana'], flavorGear: ['Focus item', 'Arcane notes'] },
  ],
  personalityFormat: 'simple',
  skills: [
    { id: 'arcana', name: 'Arcana' }, { id: 'athletics', name: 'Athletics' },
    { id: 'close combat', name: 'Close Combat' }, { id: 'computers', name: 'Computers' },
    { id: 'con', name: 'Con' }, { id: 'cracking', name: 'Cracking' },
    { id: 'electronics', name: 'Electronics' }, { id: 'engineering', name: 'Engineering' },
    { id: 'etiquette (corporate)', name: 'Etiquette (Corporate)' },
    { id: 'etiquette (street)', name: 'Etiquette (Street)' },
    { id: 'firearms', name: 'Firearms' }, { id: 'intimidation', name: 'Intimidation' },
    { id: 'medicine', name: 'Medicine' }, { id: 'perception', name: 'Perception' },
    { id: 'piloting', name: 'Piloting' }, { id: 'spellcasting', name: 'Spellcasting' },
    { id: 'stealth', name: 'Stealth' }, { id: 'streetwise', name: 'Streetwise' },
  ],
  skillCount: 5,
  gearPackages: [
    { id: 'runner', name: 'Runner Basics', items: ['Commlink', 'Armor jacket', 'Holdout pistol', 'Credstick (500¥)', 'Fake SIN (Rating 2)'] },
  ],
  levelRange: [1, 6],
}

// ─────────────────────────────────────────────
// Master system registry
// ─────────────────────────────────────────────

export const WIZARD_SYSTEMS: WizardSystem[] = [
  DND5E, PF2E, PF1E, STARFINDER, COC, STARTREK, SOTDL, WFRP, ALIEN, SHADOWRUN,
]

export function getSystem(id: SystemId): WizardSystem | undefined {
  return WIZARD_SYSTEMS.find((s) => s.id === id)
}

/** Score background quiz answers and return backgroundId sorted by score (highest first). */
export function scoreBackgroundQuiz(
  system: WizardSystem,
  answers: Record<string, string>, // questionId → optionId
): string[] {
  const totals: Record<string, number> = {}
  for (const [qId, optionId] of Object.entries(answers)) {
    const question = system.backgroundQuiz.find((q) => q.id === qId)
    if (!question) continue
    const option = question.options.find((o) => o.id === optionId)
    if (!option) continue
    for (const [bgId, score] of Object.entries(option.scores)) {
      totals[bgId] = (totals[bgId] ?? 0) + score
    }
  }
  return Object.entries(totals)
    .sort((a, b) => b[1] - a[1])
    .map(([id]) => id)
}

// ─────────────────────────────────────────────
// Campaign Creation Wizard
// ─────────────────────────────────────────────

export type CampaignQuizOption = {
  id: string
  text: string
  emoji: string
  /** Maps result keys → values accumulated from this choice */
  signals: Partial<{
    tone: string
    genre: string
    pacing: string
    content_rating: string
  }>
}

export type CampaignQuizQuestion = {
  id: string
  scene: string   // narrative framing ("Your party enters the inn…")
  prompt: string  // the actual question
  options: CampaignQuizOption[]
}

export const CAMPAIGN_QUIZ: CampaignQuizQuestion[] = [
  {
    id: 'q_atmosphere',
    scene: 'Your party is about to begin. You push open the door of The Broken Tankard tavern…',
    prompt: 'What greets you inside?',
    options: [
      { id: 'a', text: 'Roaring laughter, clinking mugs, and a bard on the table', emoji: '🍺', signals: { tone: 'heroic', pacing: 'fast' } },
      { id: 'b', text: 'Hushed voices, hooded figures, and suspicious glances your way', emoji: '🕵️', signals: { tone: 'grim', genre: 'thriller' } },
      { id: 'c', text: 'Flickering candles, frost on the windows, and locals who won\'t meet your eyes', emoji: '🕯️', signals: { tone: 'horror', genre: 'horror' } },
      { id: 'd', text: 'Neon signs and synthesized music — this is definitely not a medieval tavern', emoji: '🌆', signals: { genre: 'sci-fi', tone: 'thriller' } },
    ],
  },
  {
    id: 'q_offer',
    scene: 'A cloaked figure slides into your booth. They push a coin pouch across the table.',
    prompt: 'What do they want?',
    options: [
      { id: 'a', text: 'Help slaying the creature terrorizing nearby villages', emoji: '⚔️', signals: { tone: 'heroic', genre: 'fantasy' } },
      { id: 'b', text: 'Something stolen from someone powerful — no questions asked', emoji: '🗝️', signals: { tone: 'grim', genre: 'thriller' } },
      { id: 'c', text: 'To investigate something impossible — something the authorities won\'t touch', emoji: '🔍', signals: { tone: 'grim', genre: 'mystery' } },
      { id: 'd', text: 'Something you haven\'t agreed to yet. They say you\'ll understand when you arrive', emoji: '😰', signals: { tone: 'horror', genre: 'horror' } },
    ],
  },
  {
    id: 'q_threat',
    scene: 'Beyond the immediate job, a shadow looms over the land.',
    prompt: 'What is the world\'s greatest problem?',
    options: [
      { id: 'a', text: 'A rising dark lord marshaling their armies in the north', emoji: '🏰', signals: { genre: 'fantasy', tone: 'heroic' } },
      { id: 'b', text: 'Corrupt nobles squeezing the life from the common people', emoji: '👑', signals: { genre: 'political', tone: 'grim' } },
      { id: 'c', text: 'Ancient horrors awakening from beneath the earth', emoji: '🐙', signals: { genre: 'horror', tone: 'horror' } },
      { id: 'd', text: 'A cold war between empires on the edge of catastrophic conflict', emoji: '💣', signals: { genre: 'thriller', tone: 'grim' } },
    ],
  },
  {
    id: 'q_combat',
    scene: 'Your fighter Bob squares off against a formidable enemy.',
    prompt: 'How does this fight feel?',
    options: [
      { id: 'a', text: 'Cinematic and epic — someone\'s definitely getting a hero moment', emoji: '🌟', signals: { tone: 'heroic', pacing: 'fast' } },
      { id: 'b', text: 'Brutal and desperate — everyone might actually die here', emoji: '💀', signals: { tone: 'grim', content_rating: 'r' } },
      { id: 'c', text: 'A strategic chess match — positioning and planning matter most', emoji: '♟️', signals: { pacing: 'moderate', tone: 'grim' } },
      { id: 'd', text: 'Absolute comedic chaos — shields flying, spells backfiring', emoji: '🤣', signals: { tone: 'comedy', pacing: 'fast' } },
    ],
  },
  {
    id: 'q_world',
    scene: 'The camera pulls back to reveal your entire campaign world from above.',
    prompt: 'What does it look like?',
    options: [
      { id: 'a', text: 'Vast continents: ancient ruins, deep forests, dragon-haunted mountains', emoji: '🗺️', signals: { genre: 'fantasy' } },
      { id: 'b', text: 'A dense urban maze of guilds, underground crime, and political intrigue', emoji: '🏙️', signals: { genre: 'political', tone: 'grim' } },
      { id: 'c', text: 'Stars, starships, alien worlds, and the infinite dark between them', emoji: '🚀', signals: { genre: 'sci-fi' } },
      { id: 'd', text: 'Crumbling civilization — the old world is gone, something new struggles to emerge', emoji: '🌋', signals: { genre: 'post-apocalyptic', tone: 'grim' } },
    ],
  },
]

/**
 * Given campaign quiz answers, derive suggested campaign settings.
 * Returns object with `tone`, `genre`, `pacing`, `content_rating` populated
 * from the most-signaled values.
 */
export function deriveCampaignSettings(answers: Record<string, string>): {
  tone: string
  genre: string
  pacing: string
  content_rating: string
  setting_summary: string
} {
  const scores: Record<string, Record<string, number>> = {
    tone: {}, genre: {}, pacing: {}, content_rating: {},
  }

  for (const [qId, optionId] of Object.entries(answers)) {
    const question = CAMPAIGN_QUIZ.find((q) => q.id === qId)
    if (!question) continue
    const option = question.options.find((o) => o.id === optionId)
    if (!option) continue
    for (const [key, val] of Object.entries(option.signals)) {
      if (val) {
        scores[key][val] = (scores[key][val] ?? 0) + 1
      }
    }
  }

  const pick = (cat: string, fallback: string) => {
    const entries = Object.entries(scores[cat] ?? {})
    if (!entries.length) return fallback
    return entries.sort((a, b) => b[1] - a[1])[0][0]
  }

  const tone = pick('tone', 'heroic')
  const genre = pick('genre', 'fantasy')
  const pacing = pick('pacing', 'moderate')
  const content_rating = pick('content_rating', 'pg-13')

  const toneLabel: Record<string, string> = {
    heroic: 'heroic epic',
    grim: 'grim and grounded',
    horror: 'dread-filled horror',
    comedy: 'light-hearted comedy',
    thriller: 'edge-of-your-seat thriller',
    political: 'political intrigue',
  }
  const genreLabel: Record<string, string> = {
    fantasy: 'high fantasy',
    horror: 'cosmic horror',
    'sci-fi': 'science fiction',
    mystery: 'mystery',
    thriller: 'thriller',
    political: 'political drama',
    'post-apocalyptic': 'post-apocalyptic survival',
  }

  const setting_summary = `A ${toneLabel[tone] ?? tone} campaign set in a world of ${genreLabel[genre] ?? genre}. The stakes are personal and the world is dangerous — every choice matters.`

  return { tone, genre, pacing, content_rating, setting_summary }
}
