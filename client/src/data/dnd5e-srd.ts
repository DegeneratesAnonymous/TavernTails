/**
 * dnd5e-srd.ts
 * System Reference Library — D&D 5e (SRD 5.1, CC BY 4.0, Wizards of the Coast)
 *
 * Contains mechanical summaries for feats, class level-1 features, and ancestry
 * traits. All text is original mechanical description, not verbatim SRD prose.
 *
 * Attribution: Dungeons & Dragons 5th Edition SRD 5.1 — https://dnd.wizards.com/resources/systems-reference-document
 * Licensed under CC BY 4.0 — https://creativecommons.org/licenses/by/4.0/
 */

// ─────────────────────────────────────────────
// Shared types
// ─────────────────────────────────────────────

export type FeatTag = 'combat' | 'magic' | 'utility' | 'social'

export type FeatOption = {
  id: string
  name: string
  /** Requirement that must be met before selecting this feat */
  prerequisite?: string
  /** Concise mechanical benefit (not verbatim rules text) */
  benefit: string
  tags: FeatTag[]
}

export type ClassFeature = {
  name: string
  level: number
  summary: string
}

export type AncestryTrait = {
  name: string
  summary: string
}

// ─────────────────────────────────────────────
// D&D 5e Feats (SRD 5.1 subset)
// ─────────────────────────────────────────────

export const DND5E_FEATS: FeatOption[] = [
  {
    id: 'alert',
    name: 'Alert',
    benefit: '+5 to initiative; cannot be surprised while conscious; hidden attackers gain no advantage on attack rolls against you.',
    tags: ['combat', 'utility'],
  },
  {
    id: 'athlete',
    name: 'Athlete',
    prerequisite: 'STR or DEX 13+',
    benefit: '+1 STR or DEX. Climbing and crawling cost no extra movement. Standing up from prone costs only 5 ft. Running start for long/high jump requires only 5 ft.',
    tags: ['combat', 'utility'],
  },
  {
    id: 'actor',
    name: 'Actor',
    benefit: '+1 CHA. Advantage on Deception and Performance when impersonating a person or creature. Can mimic voices or sounds with a successful Insight check (DC 8 + Insight).',
    tags: ['social', 'utility'],
  },
  {
    id: 'charger',
    name: 'Charger',
    benefit: 'After using the Dash action, make one weapon attack or shove as a bonus action. If you moved 10+ ft in a straight line before attacking, add +5 damage or push the target 10 ft.',
    tags: ['combat'],
  },
  {
    id: 'crossbow_expert',
    name: 'Crossbow Expert',
    benefit: 'Ignore the loading property on crossbows you are proficient with. No disadvantage when making ranged attacks within 5 ft of an enemy. When you use the Attack action with a one-handed weapon, you can use a bonus action to attack with a hand crossbow.',
    tags: ['combat'],
  },
  {
    id: 'defensive_duelist',
    name: 'Defensive Duelist',
    prerequisite: 'DEX 13+',
    benefit: 'When attacked while holding a finesse weapon you are proficient with, use your reaction to add your proficiency bonus to your AC against that attack.',
    tags: ['combat'],
  },
  {
    id: 'dual_wielder',
    name: 'Dual Wielder',
    benefit: '+1 AC while holding a melee weapon in each hand. You can use two-weapon fighting even if the weapons are not light. Draw or stow two weapons at once.',
    tags: ['combat'],
  },
  {
    id: 'dungeon_delver',
    name: 'Dungeon Delver',
    benefit: 'Advantage on Perception and Investigation checks to detect secret doors. Advantage on saves against traps; resistance to trap damage. Search for traps at normal travel pace.',
    tags: ['utility'],
  },
  {
    id: 'durable',
    name: 'Durable',
    benefit: '+1 CON. When you roll a Hit Die on a short rest, the minimum HP you regain equals twice your CON modifier (min 2).',
    tags: ['utility'],
  },
  {
    id: 'elemental_adept',
    name: 'Elemental Adept',
    prerequisite: 'Spellcasting ability',
    benefit: 'Choose one damage type: acid, cold, fire, lightning, or thunder. Your spells ignore resistance to that damage type. Treat 1s on damage dice as 2s for spells of that type. Can be taken multiple times for different damage types.',
    tags: ['magic'],
  },
  {
    id: 'grappler',
    name: 'Grappler',
    prerequisite: 'STR 13+',
    benefit: 'Advantage on attack rolls against creatures you are grappling. Use your action to restrain a creature you are grappling (both becomes restrained until it ends).',
    tags: ['combat'],
  },
  {
    id: 'great_weapon_master',
    name: 'Great Weapon Master',
    benefit: 'On a critical hit or killing blow with a heavy melee weapon, make one additional attack as a bonus action this turn. Before a melee attack with a heavy weapon, take −5 to the roll for +10 damage on hit.',
    tags: ['combat'],
  },
  {
    id: 'healer',
    name: 'Healer',
    benefit: 'Stabilize a creature with a healer\'s kit as a bonus action (rather than an action). Use a healer\'s kit as an action to restore 1d6 + 4 + target\'s max HD in HP (once per short/long rest per target).',
    tags: ['utility'],
  },
  {
    id: 'heavily_armored',
    name: 'Heavily Armored',
    prerequisite: 'Proficiency with medium armor',
    benefit: '+1 STR. Gain proficiency with heavy armor.',
    tags: ['combat'],
  },
  {
    id: 'heavy_armor_master',
    name: 'Heavy Armor Master',
    prerequisite: 'Proficiency with heavy armor',
    benefit: '+1 STR. While wearing heavy armor, reduce incoming bludgeoning, piercing, and slashing damage from nonmagical attacks by 3.',
    tags: ['combat'],
  },
  {
    id: 'inspiring_leader',
    name: 'Inspiring Leader',
    prerequisite: 'CHA 13+',
    benefit: 'Spend 10 minutes giving an inspiring speech. Up to 6 friendly creatures who can hear and understand you gain temporary HP equal to your level + CHA modifier.',
    tags: ['social', 'utility'],
  },
  {
    id: 'keen_mind',
    name: 'Keen Mind',
    benefit: '+1 INT. Always know which direction is north. Always know how many hours remain until sunrise or sunset. Recall anything you have seen or heard within the past month.',
    tags: ['utility'],
  },
  {
    id: 'lightly_armored',
    name: 'Lightly Armored',
    benefit: '+1 STR or DEX. Gain proficiency with light armor.',
    tags: ['utility'],
  },
  {
    id: 'linguist',
    name: 'Linguist',
    benefit: '+1 INT. Learn 3 additional languages. Can create written ciphers; others need an INT check (DC = your INT score) to decipher them.',
    tags: ['utility', 'social'],
  },
  {
    id: 'lucky',
    name: 'Lucky',
    benefit: '3 luck points per long rest. Before a d20 roll (or after a creature rolls against you), spend a point to roll an additional d20 and choose which result to use.',
    tags: ['utility', 'combat'],
  },
  {
    id: 'mage_slayer',
    name: 'Mage Slayer',
    benefit: 'When a creature within 5 ft casts a spell, use your reaction to make a melee attack against them. That creature has disadvantage on Constitution saves to maintain concentration. You have advantage on saves against spells from creatures within 5 ft of you.',
    tags: ['combat', 'magic'],
  },
  {
    id: 'magic_initiate',
    name: 'Magic Initiate',
    benefit: 'Choose a class: learn 2 cantrips from that class\'s spell list. Choose one 1st-level spell from that list; cast it once per long rest without a spell slot at its lowest level.',
    tags: ['magic'],
  },
  {
    id: 'martial_adept',
    name: 'Martial Adept',
    benefit: 'Learn 2 maneuvers from the Battle Master fighter subclass list. Gain one superiority die (d6), which recharges on a short or long rest.',
    tags: ['combat'],
  },
  {
    id: 'medium_armor_master',
    name: 'Medium Armor Master',
    prerequisite: 'Proficiency with medium armor',
    benefit: 'No disadvantage on Stealth checks while wearing medium armor. The maximum DEX bonus to AC from medium armor increases to +3.',
    tags: ['combat'],
  },
  {
    id: 'mobile',
    name: 'Mobile',
    benefit: '+10 ft to speed. When you use the Dash action, difficult terrain doesn\'t cost extra movement this turn. When you make a melee attack against a creature, you don\'t provoke opportunity attacks from that creature until the end of your turn.',
    tags: ['combat'],
  },
  {
    id: 'moderately_armored',
    name: 'Moderately Armored',
    prerequisite: 'Proficiency with light armor',
    benefit: '+1 STR or DEX. Gain proficiency with medium armor and shields.',
    tags: ['combat'],
  },
  {
    id: 'mounted_combatant',
    name: 'Mounted Combatant',
    benefit: 'Advantage on melee attack rolls against unmounted creatures smaller than your mount. Force attacks targeting your mount to target you instead. Mount can apply failed Dex saves as half damage, and no damage on success.',
    tags: ['combat'],
  },
  {
    id: 'observant',
    name: 'Observant',
    benefit: '+1 INT or WIS. If you can see a creature\'s mouth while it speaks a language you know, you can interpret what it says by lip-reading. +5 to passive Perception and passive Investigation scores.',
    tags: ['utility'],
  },
  {
    id: 'polearm_master',
    name: 'Polearm Master',
    benefit: 'When you take the Attack action with a glaive, halberd, quarterstaff, or spear, make a bonus attack with the butt end (1d4 bludgeoning). Creatures entering your reach provoke an opportunity attack from your polearm.',
    tags: ['combat'],
  },
  {
    id: 'resilient',
    name: 'Resilient',
    benefit: '+1 to the chosen ability score. Gain saving throw proficiency for that ability.',
    tags: ['utility'],
  },
  {
    id: 'ritual_caster',
    name: 'Ritual Caster',
    prerequisite: 'INT or WIS 13+',
    benefit: 'Gain a ritual book containing 2 first-level ritual spells. Ritual spells you find can be transcribed into the book. Cast ritual spells without spell slots (takes 10 extra minutes).',
    tags: ['magic', 'utility'],
  },
  {
    id: 'savage_attacker',
    name: 'Savage Attacker',
    benefit: 'Once per turn when you roll damage for a melee weapon attack, reroll the damage dice and use either result.',
    tags: ['combat'],
  },
  {
    id: 'sentinel',
    name: 'Sentinel',
    benefit: 'When you hit with an opportunity attack, reduce the creature\'s speed to 0 for the rest of the turn. Creatures provoke opportunity attacks even when they use Disengage. When a creature attacks a target other than you within 5 ft, use your reaction to make a melee weapon attack against that creature.',
    tags: ['combat'],
  },
  {
    id: 'sharpshooter',
    name: 'Sharpshooter',
    benefit: 'No disadvantage from long range on ranged weapon attacks. Ranged attacks ignore half cover and three-quarters cover. Before a ranged attack, take −5 to the roll for +10 damage on hit.',
    tags: ['combat'],
  },
  {
    id: 'shield_master',
    name: 'Shield Master',
    benefit: 'If you take the Attack action, shove a creature as a bonus action. Add your shield\'s AC bonus to DEX saves that target only you. On a successful DEX save where you take half damage, take no damage instead (while carrying a shield).',
    tags: ['combat'],
  },
  {
    id: 'skilled',
    name: 'Skilled',
    benefit: 'Gain proficiency in any combination of three skills or tools of your choice.',
    tags: ['utility'],
  },
  {
    id: 'skulker',
    name: 'Skulker',
    prerequisite: 'DEX 13+',
    benefit: 'Can attempt to hide when only lightly obscured. When hidden and a ranged attack misses, your position is not revealed. No disadvantage on Perception checks in dim light.',
    tags: ['combat', 'utility'],
  },
  {
    id: 'spell_sniper',
    name: 'Spell Sniper',
    prerequisite: 'Spellcasting ability',
    benefit: 'Double the range of attack-roll spells. Ranged spell attacks ignore half cover and three-quarters cover. Learn one attack-roll cantrip from the chosen class\'s spell list.',
    tags: ['magic', 'combat'],
  },
  {
    id: 'tavern_brawler',
    name: 'Tavern Brawler',
    benefit: '+1 STR or CON. Proficient with improvised weapons. Unarmed strikes deal 1d4 bludgeoning. After an unarmed or improvised weapon hit, attempt a grapple as a bonus action.',
    tags: ['combat'],
  },
  {
    id: 'tough',
    name: 'Tough',
    benefit: 'HP maximum increases by 2 per character level (retroactive). This bonus increases by 2 each time you gain a level.',
    tags: ['utility', 'combat'],
  },
  {
    id: 'war_caster',
    name: 'War Caster',
    prerequisite: 'Spellcasting ability',
    benefit: 'Advantage on Constitution saves to maintain concentration. Perform somatic components while wielding weapons or a shield. When a creature provokes an opportunity attack, cast a spell targeting that creature instead of making a melee attack.',
    tags: ['magic', 'combat'],
  },
  {
    id: 'weapon_master',
    name: 'Weapon Master',
    benefit: '+1 STR or DEX. Gain proficiency with 4 weapons of your choice.',
    tags: ['combat'],
  },
]

// ─────────────────────────────────────────────
// D&D 5e Class Features (Level 1, SRD 5.1)
// ─────────────────────────────────────────────

export const DND5E_CLASS_FEATURES: Record<string, ClassFeature[]> = {
  artificer: [
    {
      name: 'Magical Tinkering',
      level: 1,
      summary:
        'Imbue a Tiny nonmagical object with one of four minor magical properties: emit light, emit a recorded message (≤6 sec), emit a smell or nonverbal sound, or display a visual effect. Imbued objects equal to your INT modifier active at once.',
    },
    {
      name: 'Spellcasting',
      level: 2,
      summary:
        'INT-based spellcasting using tools as a focus. Spellcasting begins at level 2; prepare spells equal to INT modifier + half artificer level. Half-caster progression.',
    },
  ],
  barbarian: [
    {
      name: 'Rage',
      level: 1,
      summary:
        'Bonus action: enter a rage for up to 1 minute. During rage: advantage on STR checks and STR saves, bonus damage on STR-based melee attacks (+2/+3/+4 scaling), resistance to bludgeoning/piercing/slashing damage. Ends early if unconscious or you end a turn without attacking or being attacked. Uses per long rest = 2 (scales with level).',
    },
    {
      name: 'Unarmored Defense',
      level: 1,
      summary:
        'While not wearing armor, your AC equals 10 + DEX modifier + CON modifier. You may still use a shield.',
    },
  ],
  bard: [
    {
      name: 'Spellcasting',
      level: 1,
      summary:
        'CHA-based spellcasting using a musical instrument as a focus. Know 2 spells and 4 cantrips at level 1; spells known increase with level. Full spellcaster progression.',
    },
    {
      name: 'Bardic Inspiration',
      level: 1,
      summary:
        'Bonus action: grant one creature within 60 ft an Inspiration Die (d6). The creature can add it to one ability check, attack roll, or saving throw within the next 10 minutes. Uses per long rest = CHA modifier. Die size increases at levels 5 (d8), 10 (d10), 15 (d12).',
    },
  ],
  cleric: [
    {
      name: 'Spellcasting',
      level: 1,
      summary:
        'WIS-based spellcasting using a holy symbol as a focus. Prepare spells each day equal to WIS modifier + cleric level. Full spellcaster progression. Domain spells are always prepared.',
    },
    {
      name: 'Divine Domain',
      level: 1,
      summary:
        'Choose a divine domain (e.g. Life, War, Trickery). Grants 2 domain spells at levels 1, 3, 5, 7, 9 (always prepared), and additional domain features at levels 1, 2, 6, 8, 17.',
    },
  ],
  druid: [
    {
      name: 'Druidic',
      level: 1,
      summary:
        'You know the secret Druidic language. Can leave hidden messages in nature (noticed with DC 15 Perception; readable only to other druids).',
    },
    {
      name: 'Spellcasting',
      level: 1,
      summary:
        'WIS-based spellcasting using a druidic focus. Prepare spells each day equal to WIS modifier + druid level. Full spellcaster progression. Druids cannot cast spells in metal armor.',
    },
  ],
  fighter: [
    {
      name: 'Fighting Style',
      level: 1,
      summary:
        'Choose one fighting specialization: Archery (+2 to ranged attack rolls), Defense (+1 AC in armor), Dueling (+2 damage with one-handed weapon and no other weapon), Great Weapon Fighting (reroll 1s and 2s on damage dice for two-handed melee), Protection (impose disadvantage on an attack against an adjacent ally as a reaction while using a shield), Two-Weapon Fighting (add ability modifier to off-hand damage).',
    },
    {
      name: 'Second Wind',
      level: 1,
      summary:
        'Bonus action: regain HP equal to 1d10 + fighter level. One use per short or long rest.',
    },
  ],
  monk: [
    {
      name: 'Unarmored Defense',
      level: 1,
      summary:
        'While not wearing armor or using a shield, your AC equals 10 + DEX modifier + WIS modifier.',
    },
    {
      name: 'Martial Arts',
      level: 1,
      summary:
        'With unarmed strikes or monk weapons: use DEX instead of STR for attack/damage rolls; the damage die is d4 (scales with level). After taking the Attack action with an unarmed strike or monk weapon, make one unarmed strike as a bonus action.',
    },
  ],
  paladin: [
    {
      name: 'Divine Sense',
      level: 1,
      summary:
        'Action: until end of your next turn, know the location of celestials, fiends, and undead within 60 ft that are not behind total cover. Uses per long rest = 1 + CHA modifier.',
    },
    {
      name: 'Lay on Hands',
      level: 1,
      summary:
        'Healing pool of HP = 5 × paladin level. Touch a creature to restore HP from the pool (any amount). Or expend 5 HP worth to cure one disease or poison. No effect on constructs or undead.',
    },
  ],
  ranger: [
    {
      name: 'Favored Enemy',
      level: 1,
      summary:
        'Choose a creature type (or two humanoid types). Advantage on Survival checks to track them and INT checks to recall lore about them. Learn one language spoken by one favored enemy type.',
    },
    {
      name: 'Natural Explorer',
      level: 1,
      summary:
        'Choose a favored terrain type. In that terrain: double proficiency on INT/WIS checks using skills you are proficient in; difficult terrain doesn\'t slow group travel; group can\'t become lost except by magic; alert to danger before others; move stealthily at normal pace; find double food foraging; learn exact creature numbers when tracking.',
    },
  ],
  rogue: [
    {
      name: 'Expertise',
      level: 1,
      summary:
        'Choose 2 skill proficiencies (or 1 skill + Thieves\' Tools). Double your proficiency bonus for those skills. Choose 2 more at level 6.',
    },
    {
      name: 'Sneak Attack',
      level: 1,
      summary:
        'Once per turn, deal an extra 1d6 damage to one creature you hit with a finesse or ranged weapon attack if you have advantage on the roll, or if an ally is within 5 ft of the target and you do not have disadvantage. Damage increases by 1d6 every 2 levels.',
    },
    {
      name: "Thieves' Cant",
      level: 1,
      summary:
        'You know Thieves\' Cant, a secret criminal argot. Can exchange information hidden within ordinary conversation. Takes 4× as long to convey the same content.',
    },
  ],
  sorcerer: [
    {
      name: 'Spellcasting',
      level: 1,
      summary:
        'CHA-based spellcasting using an arcane focus. Know 4 cantrips and 2 spells at level 1; spells known scale with level. Full spellcaster progression.',
    },
    {
      name: 'Sorcerous Origin',
      level: 1,
      summary:
        'Choose a magical bloodline (e.g. Draconic Bloodline, Wild Magic). Grants bonus features at levels 1, 6, 14, and 18.',
    },
  ],
  warlock: [
    {
      name: 'Otherworldly Patron',
      level: 1,
      summary:
        'Bargain with a powerful patron (Archfey, Fiend, or Great Old One). Grants an expanded spell list and patron-specific features at levels 1, 6, 10, and 14.',
    },
    {
      name: 'Pact Magic',
      level: 1,
      summary:
        'CHA-based spellcasting using an arcane focus. Spell slots are always at maximum level and recharge on short or long rest. 1 slot at level 1, 2 slots at level 2+. Know 2 spells at level 1.',
    },
  ],
  wizard: [
    {
      name: 'Spellcasting',
      level: 1,
      summary:
        'INT-based spellcasting using a spellbook and an arcane focus. Prepare spells each day equal to INT modifier + wizard level. Full spellcaster progression. Start with 6 spells in spellbook; copy found spells for 50 gp + 2 hours per level.',
    },
    {
      name: 'Arcane Recovery',
      level: 1,
      summary:
        'Once per day on a short rest, recover expended spell slots with a combined level equal to or less than half your wizard level (rounded up). No slot above 5th level.',
    },
  ],
}

// ─────────────────────────────────────────────
// D&D 5e Ancestry Traits (SRD 5.1)
// ─────────────────────────────────────────────

export const DND5E_ANCESTRY_TRAITS: Record<string, AncestryTrait[]> = {
  human: [
    { name: 'Ability Score Increase', summary: 'All six ability scores increase by 1.' },
    { name: 'Extra Language', summary: 'Learn one additional language of your choice.' },
  ],
  elf: [
    { name: 'Darkvision', summary: 'See in dim light as bright light and in darkness as dim light, up to 60 ft.' },
    { name: 'Keen Senses', summary: 'Proficiency in the Perception skill.' },
    { name: 'Fey Ancestry', summary: 'Advantage on saving throws against being charmed. Magic cannot put you to sleep.' },
    { name: 'Trance', summary: 'Elves do not sleep; instead meditate in a semiconscious state for 4 hours, gaining the same benefit as 8 hours of sleep.' },
  ],
  dwarf: [
    { name: 'Darkvision', summary: 'See in dim light as bright light and in darkness as dim light, up to 60 ft.' },
    { name: 'Dwarven Resilience', summary: 'Advantage on saving throws against poison. Resistance to poison damage.' },
    { name: 'Dwarven Combat Training', summary: 'Proficiency with the battleaxe, handaxe, light hammer, and warhammer.' },
    { name: 'Stonecunning', summary: 'Double proficiency bonus on History checks related to stonework.' },
  ],
  halfling: [
    { name: 'Lucky', summary: 'When you roll a 1 on an attack roll, ability check, or saving throw, reroll and use the new result.' },
    { name: 'Brave', summary: 'Advantage on saving throws against being frightened.' },
    { name: 'Halfling Nimbleness', summary: 'Can move through the space of any creature one size larger than you.' },
  ],
  gnome: [
    { name: 'Darkvision', summary: 'See in dim light as bright light and in darkness as dim light, up to 60 ft.' },
    { name: 'Gnome Cunning', summary: 'Advantage on all INT, WIS, and CHA saving throws against magic.' },
  ],
  'half-elf': [
    { name: 'Darkvision', summary: 'See in dim light as bright light and in darkness as dim light, up to 60 ft.' },
    { name: 'Fey Ancestry', summary: 'Advantage on saving throws against being charmed. Magic cannot put you to sleep.' },
    { name: 'Skill Versatility', summary: 'Proficiency in two skills of your choice.' },
  ],
  'half-orc': [
    { name: 'Darkvision', summary: 'See in dim light as bright light and in darkness as dim light, up to 60 ft.' },
    { name: 'Menacing', summary: 'Proficiency in the Intimidation skill.' },
    { name: 'Relentless Endurance', summary: 'Once per long rest, when you are reduced to 0 HP but not killed outright, drop to 1 HP instead.' },
    { name: 'Savage Attacks', summary: 'On a critical hit with a melee weapon, roll one of the weapon\'s damage dice an additional time and add it to the damage.' },
  ],
  tiefling: [
    { name: 'Darkvision', summary: 'See in dim light as bright light and in darkness as dim light, up to 60 ft.' },
    { name: 'Hellish Resistance', summary: 'Resistance to fire damage.' },
    {
      name: 'Infernal Legacy',
      summary:
        'Know the Thaumaturgy cantrip. At level 3: cast Hellish Rebuke as a 2nd-level spell (1/long rest). At level 5: cast Darkness (1/long rest). CHA is the spellcasting ability.',
    },
  ],
  dragonborn: [
    {
      name: 'Breath Weapon',
      summary:
        'Action: exhale destructive energy in a 15-ft cone or 5×30-ft line (based on draconic ancestry). Creatures in the area make a Dex or Con save (DC = 8 + CON modifier + proficiency); take 2d6 damage on failure, half on success. Can use once per short or long rest. Damage increases to 3d6 at level 6, 4d6 at level 11, 5d6 at level 16.',
    },
    {
      name: 'Damage Resistance',
      summary: 'Resistance to the damage type associated with your draconic ancestry (acid, cold, fire, lightning, or poison).',
    },
  ],
  'other': [
    { name: 'Custom Traits', summary: 'Traits vary by species. Consult your GM or the relevant sourcebook for this ancestry\'s features.' },
  ],
}

// ─────────────────────────────────────────────
// D&D 5e Hit Dice by class (SRD 5.1)
// ─────────────────────────────────────────────

export const DND5E_HIT_DICE: Record<string, number> = {
  artificer: 8,
  barbarian: 12,
  bard: 8,
  cleric: 8,
  druid: 8,
  fighter: 10,
  monk: 8,
  paladin: 10,
  ranger: 10,
  rogue: 8,
  sorcerer: 6,
  warlock: 8,
  wizard: 6,
}
