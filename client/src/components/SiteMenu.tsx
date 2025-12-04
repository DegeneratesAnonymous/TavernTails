import React from 'react'

type MenuItem = {
  key: string
  label: string
  description?: string
}

type MenuSection = {
  title: string
  items: MenuItem[]
}

type Props = {
  onNavigate?: (key: string) => void
  onClose?: () => void
}

const sections: MenuSection[] = [
  {
    title: 'Campaign',
    items: [
      {key: 'campaigns', label: 'Campaigns', description: 'Load adventures & manage settings'},
      {key: 'adventure', label: 'Adventure Settings', description: 'Tone, pacing, safety tools'},
    ],
  },
  {
    title: 'Characters',
    items: [
      {key: 'characters', label: 'Characters', description: 'View, edit, and create heroes'},
    ],
  },
  {
    title: 'Tools',
    items: [
      {key: 'map', label: 'Maps', description: 'Battle maps, world overviews'},
      {key: 'inventory', label: 'Inventory', description: 'Loot, gear, consumables'},
      {key: 'journal', label: 'Journal', description: 'Session notes & quests'},
    ],
  },
]

export default function SiteMenu({onNavigate, onClose}: Props){
  const handleSelect = (key: string) => {
    onNavigate?.(key)
    onClose?.()
  }

  return (
    <div className="site-menu-panel">
      <header className="site-menu-header">
        <div>
          <div className="site-menu-title">Command Drawer</div>
          <div className="site-menu-subtitle">Jump to characters, campaigns, or tools</div>
        </div>
        <button className="site-menu-close" onClick={onClose} aria-label="Close menu">
          ✕
        </button>
      </header>
      {sections.map(section => (
        <section key={section.title} className="site-menu-section">
          <div className="site-menu-section-title">{section.title}</div>
          <ul className="site-menu-list">
            {section.items.map(item => (
              <li key={item.key}>
                <button className="site-menu-item" onClick={() => handleSelect(item.key)}>
                  <span className="site-menu-item-label">{item.label}</span>
                  {item.description && <span className="site-menu-item-description">{item.description}</span>}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}
