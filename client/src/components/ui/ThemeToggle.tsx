import React, { useEffect, useRef, useState } from 'react'
import { THEMES, useTheme } from '../../contexts/ThemeContext'

/**
 * ThemeToggle — compact popover button for switching UI themes.
 * Drop it anywhere in a toolbar or nav.
 */
export default function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const current = THEMES.find(t => t.id === theme) ?? THEMES[0]

  useEffect(() => {
    if (!open) return
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open])

  return (
    <div ref={ref} style={{ position: 'relative', display: 'inline-block' }}>
      <button
        type="button"
        className="topbar-icon-btn"
        aria-label={`Theme: ${current.label}. Click to change.`}
        title={`Theme: ${current.label}`}
        onClick={() => setOpen(o => !o)}
        style={{ fontSize: 16 }}
      >
        {current.icon}
      </button>

      {open && (
        <div className="theme-toggle-popover">
          <div className="theme-toggle-label">Choose Theme</div>
          {THEMES.map(t => (
            <button
              key={t.id}
              type="button"
              className={`theme-toggle-option${theme === t.id ? ' theme-toggle-option--active' : ''}`}
              onClick={() => { setTheme(t.id); setOpen(false) }}
            >
              <span className="theme-toggle-option-icon">{t.icon}</span>
              <span className="theme-toggle-option-text">
                <span className="theme-toggle-option-name">{t.label}</span>
                <span className="theme-toggle-option-desc">{t.description}</span>
              </span>
              {theme === t.id && <span className="theme-toggle-check">✓</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
