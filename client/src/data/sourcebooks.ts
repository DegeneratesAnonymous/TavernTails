/** Maps DDB PDF source abbreviations → full book title. */
export const SOURCE_BOOK_NAMES: Record<string, string> = {
  // Core D&D 5e (2014)
  PHB: "Player's Handbook",
  DMG: "Dungeon Master's Guide",
  MM: 'Monster Manual',

  // Core D&D 5e (2024)
  PHB24: "Player's Handbook (2024)",
  DMG24: "Dungeon Master's Guide (2024)",
  MM25: 'Monster Manual (2025)',

  // Settings & supplements
  XGE: "Xanathar's Guide to Everything",
  XGTE: "Xanathar's Guide to Everything",
  TCoE: "Tasha's Cauldron of Everything",
  TCE: "Tasha's Cauldron of Everything",
  MToF: "Mordenkainen's Tome of Foes",
  MTOF: "Mordenkainen's Tome of Foes",
  VGtM: "Volo's Guide to Monsters",
  VGTM: "Volo's Guide to Monsters",
  EGtW: "Explorer's Guide to Wildemount",
  EGTW: "Explorer's Guide to Wildemount",
  GGtR: "Guildmasters' Guide to Ravnica",
  GGTR: "Guildmasters' Guide to Ravnica",
  MOT: 'Mythic Odysseys of Theros',
  ERLW: 'Eberron: Rising from the Last War',
  WGtE: "Wayfinder's Guide to Eberron",
  AI: 'Acquisitions Incorporated',
  SCAG: "Sword Coast Adventurer's Guide",
  BGDIA: "Baldur's Gate: Descent into Avernus",
  BGDiA: "Baldur's Gate: Descent into Avernus",
  BGDI: "Baldur's Gate: Descent into Avernus",
  IDRotF: 'Icewind Dale: Rime of the Frostmaiden',
  IDROTF: 'Icewind Dale: Rime of the Frostmaiden',
  FToD: "Fizban's Treasury of Dragons",
  FTOD: "Fizban's Treasury of Dragons",
  SCoC: 'Strixhaven: A Curriculum of Chaos',
  SCOC: 'Strixhaven: A Curriculum of Chaos',
  CRCotN: 'Critical Role: Call of the Netherdeep',
  SotDQ: 'Dragonlance: Shadow of the Dragon Queen',
  SOTDQ: 'Dragonlance: Shadow of the Dragon Queen',
  DSotDQ: 'Dragonlance: Shadow of the Dragon Queen',
  BAM: 'Spelljammer: Adventures in Space',
  SJA: 'Spelljammer: Adventures in Space',
  BoMT: 'The Book of Many Things',
  KftGV: 'Keys from the Golden Vault',
  MPMotM: "Mordenkainen Presents: Monsters of the Multiverse",
  MPMOTM: "Mordenkainen Presents: Monsters of the Multiverse",
  PAItM: 'Planescape: Adventures in the Multiverse',
  ToFW: "Turn of Fortune's Wheel",
  LoDT: 'Light of Distant Stars',
  GoS: 'Ghosts of Saltmarsh',
  ToA: 'Tomb of Annihilation',
  OotA: 'Out of the Abyss',
  PotA: 'Princes of the Apocalypse',
  RoT: 'The Rise of Tiamat',
  HotDQ: 'Hoard of the Dragon Queen',
  LMoP: 'Lost Mine of Phandelver',
  SKT: "Storm King's Thunder",
  CoS: 'Curse of Strahd',
  ToD: 'Tyranny of Dragons',
  EE: 'Elemental Evil',
  EEPC: "Elemental Evil Player's Companion",
  GHLoE: 'Grim Hollow: Lairs of Etharis',

  // Misc short codes
  UA: 'Unearthed Arcana',
  SAC: 'Sage Advice Compendium',
  OGA: 'One Grung Above',
  LLK: 'Lost Laboratory of Kwalish',
  GotSF: 'Giants of the Star Forge',
  IDRoTF: 'Icewind Dale: Rime of the Frostmaiden',
}

/** Returns the full book name for a source abbreviation, or the original string if unknown. */
export function resolveSourceName(abbr: string): string {
  const key = abbr.split(/[\s,]/)[0]  // strip page number part
  return SOURCE_BOOK_NAMES[key] ?? SOURCE_BOOK_NAMES[key.toUpperCase()] ?? ''
}

/** Formats a source ref + optional page into a human-readable tooltip string. */
export function sourceTooltip(source: string): string {
  const m = source.match(/^([A-Za-z][A-Za-z0-9&]{0,10})[\s,]+(\d+.*)$/)
  const abbr = m ? m[1] : source
  const page = m ? m[2] : null
  const full = SOURCE_BOOK_NAMES[abbr] ?? SOURCE_BOOK_NAMES[abbr.toUpperCase()] ?? ''
  if (!full) return source
  return page ? `${full}, p.${page}` : full
}
