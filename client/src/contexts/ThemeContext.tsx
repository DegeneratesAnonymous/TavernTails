import React, { createContext, useContext, useEffect, useState } from 'react'

export type ThemeId = 'medieval' | 'scifi' | 'startrek' | 'neutral'

export interface ThemeOption {
  id: ThemeId
  label: string
  icon: string
  description: string
}

export const THEMES: ThemeOption[] = [
  { id: 'medieval', label: 'Medieval', icon: '⚔️', description: 'Tavern lanterns & parchment gold' },
  { id: 'scifi', label: 'Sci-Fi', icon: '🚀', description: 'Neon circuits & deep-space glow' },
  { id: 'startrek', label: 'Star Trek', icon: '🖖', description: 'LCARS panels & starship orange' },
  { id: 'neutral', label: 'Neutral', icon: '◻', description: 'Clean dark mode baseline' },
]

const STORAGE_KEY = 'tt-theme'
const DEFAULT_THEME: ThemeId = 'medieval'

interface ThemeContextValue {
  theme: ThemeId
  setTheme: (id: ThemeId) => void
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: DEFAULT_THEME,
  setTheme: () => {},
})

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<ThemeId>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored && THEMES.some(t => t.id === stored)) return stored as ThemeId
    } catch {}
    return DEFAULT_THEME
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    try { localStorage.setItem(STORAGE_KEY, theme) } catch {}
  }, [theme])

  // Apply on first mount (in case SSR or initial render)
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <ThemeContext.Provider value={{ theme, setTheme: setThemeState }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  return useContext(ThemeContext)
}
