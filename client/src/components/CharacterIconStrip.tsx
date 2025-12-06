import React from 'react'

const ICON_BASE = `${process.env.PUBLIC_URL || ''}/icons`

export type CharacterSnapshot = {
  stats: { str: number; dex: number; wis: number }
  features: string[]
  inventoryCount: number
  journalEntries: number
  skills: { name: string; mod: number }[]
}

type Props = {
  character?: CharacterSnapshot | null
}

const formatMod = (score: number) => {
  const mod = Math.floor((score - 10) / 2)
  return mod >= 0 ? `+${mod}` : `${mod}`
}

export default function CharacterIconStrip({character}: Props){
  if(!character){
    return null
  }

  const items = [
    {
      key: 'abilities',
      icon: 'Abilities.png',
      label: 'Abilities',
      value: `DEX ${formatMod(character.stats.dex)} / WIS ${formatMod(character.stats.wis)}`,
    },
    {
      key: 'features',
      icon: 'Features.png',
      label: 'Features',
      value: `${character.features.length} readied`,
    },
    {
      key: 'inventory',
      icon: 'Inventory.png',
      label: 'Inventory',
      value: `${character.inventoryCount} items`,
    },
    {
      key: 'journal',
      icon: 'Journal.png',
      label: 'Journal',
      value: `${character.journalEntries} entries`,
    },
    {
      key: 'skills',
      icon: 'Skills.png',
      label: 'Skills',
      value: character.skills.length ? `${character.skills[0].name} ${character.skills[0].mod >= 0 ? '+' : ''}${character.skills[0].mod}` : 'Set next',
    },
  ]

  return (
    <div className="character-icon-strip" aria-label="Character quick info">
      {items.map(item => (
        <div className="character-icon-card" key={item.key}>
          <img src={`${ICON_BASE}/${item.icon}`} alt={item.label} loading="lazy" />
          <div>
            <div className="character-icon-label">{item.label}</div>
            <div className="character-icon-value">{item.value}</div>
          </div>
        </div>
      ))}
    </div>
  )
}
