/**
 * ThemeSelector — compact icon-button + dropdown for switching UI themes.
 * Designed to live in the dashboard top-bar.
 */
import React, { useEffect, useRef, useState } from 'react';
import { useTheme } from '../../context/ThemeContext';
import './ThemeSelector.css';

export default function ThemeSelector() {
  const { theme, setTheme, themes } = useTheme();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const current = themes.find(t => t.id === theme)!;

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: PointerEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('pointerdown', onPointerDown);
    return () => document.removeEventListener('pointerdown', onPointerDown);
  }, [open]);

  return (
    <div className="theme-sel" ref={containerRef}>
      <button
        type="button"
        className="topbar-icon-btn theme-sel__trigger"
        aria-label={`Theme: ${current.label}. Click to change.`}
        aria-expanded={open}
        title={`Theme: ${current.label}`}
        onClick={() => setOpen(o => !o)}
      >
        🎨
      </button>

      {open && (
        <div className="theme-sel__panel" role="menu">
          <div className="theme-sel__header">UI Theme</div>
          {themes.map(t => (
            <button
              key={t.id}
              type="button"
              role="menuitem"
              className={`theme-sel__option${t.id === theme ? ' theme-sel__option--active' : ''}`}
              onClick={() => { setTheme(t.id); setOpen(false); }}
            >
              <span className="theme-sel__icon">{t.icon}</span>
              <span className="theme-sel__info">
                <span className="theme-sel__label">{t.label}</span>
                <span className="theme-sel__desc">{t.description}</span>
              </span>
              {t.id === theme && <span className="theme-sel__check">✦</span>}
            </button>
          ))}
          <div className="theme-sel__footer">More themes coming soon</div>
        </div>
      )}
    </div>
  );
}
