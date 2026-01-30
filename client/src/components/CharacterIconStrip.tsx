import React from 'react'

const ICON_BASE = `${process.env.PUBLIC_URL || ''}/icons`

export type CharacterSnapshot = {
  stats?: { str?: number; dex?: number; con?: number; int?: number; wis?: number; cha?: number }
  features?: string[]
  inventoryCount?: number
  journalEntries?: number
  skills?: { name: string; mod: number }[]
}

export type CharacterStripKey = 'abilities' | 'features' | 'inventory' | 'journal' | 'skills'

type Props = {
  character?: CharacterSnapshot | null
  activeKey?: CharacterStripKey | null
  onSelect?: (key: CharacterStripKey) => void
}

const formatMod = (score: number) => {
  const mod = Math.floor((score - 10) / 2)
  return mod >= 0 ? `+${mod}` : `${mod}`
}

const toNumber = (value: any, fallback: number) => {
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

export default function CharacterIconStrip({ character, activeKey = null, onSelect }: Props){
  if(!character){
    return null
  }

  const stats = character.stats || {}
  const str = toNumber((stats as any).str, 10)
  const dex = toNumber((stats as any).dex, 10)
  const con = toNumber((stats as any).con, 10)
  const int = toNumber((stats as any).int, 10)
  const wis = toNumber((stats as any).wis, 10)
  const cha = toNumber((stats as any).cha, 10)
  const features = Array.isArray(character.features) ? character.features : []
  const skills = Array.isArray(character.skills) ? character.skills : []
  const inventoryCount = typeof character.inventoryCount === 'number'
    ? character.inventoryCount
    : Array.isArray((character as any)?.inventory)
      ? (character as any).inventory.length
      : 0
  const journalEntries = typeof character.journalEntries === 'number' ? character.journalEntries : 0

  const items = [
    {
      key: 'abilities' as const,
      icon: 'Abilities.png',
      label: 'Abilities',
      value: `STR ${formatMod(str)} · DEX ${formatMod(dex)} · CON ${formatMod(con)}`,
    },
    {
      key: 'features' as const,
      icon: 'Features.png',
      label: 'Features',
      value: `${features.length} readied`,
    },
    {
      key: 'inventory' as const,
      icon: 'Inventory.png',
      label: 'Inventory',
      value: `${inventoryCount} items`,
    },
    {
      key: 'journal' as const,
      icon: 'Journal.png',
      label: 'Journal',
      value: `${journalEntries} entries`,
    },
    {
      key: 'skills' as const,
      icon: 'Skills.png',
      label: 'Skills',
      value: skills.length
        ? `${skills[0].name} ${skills[0].mod >= 0 ? '+' : ''}${skills[0].mod}`
        : `WIS ${formatMod(wis)} · CHA ${formatMod(cha)} · INT ${formatMod(int)}`,
    },
  ]

  return (
    <div className="character-icon-strip" aria-label="Character quick info">
      {items.map(item => (
        <button
          key={item.key}
          type="button"
          className={`character-icon-card character-icon-card--button ${item.key === activeKey ? 'character-icon-card--active' : ''}`}
          onClick={() => onSelect?.(item.key)}
          aria-pressed={item.key === activeKey}
        >
          <img src={`${ICON_BASE}/${item.icon}`} alt={item.label} loading="lazy" />
          <div>
            <div className="character-icon-label">{item.label}</div>
            <div className="character-icon-value">{item.value}</div>
          </div>
        </button>
      ))}
    </div>
  )
}
