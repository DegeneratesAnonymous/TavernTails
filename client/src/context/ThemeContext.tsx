/**
 * ThemeContext — global theme selection + persistence.
 *
 * Usage:
 *   const { theme, setTheme, themes } = useTheme();
 *
 * Adding a new theme later:
 *   1. Add an entry to THEMES below.
 *   2. Add a [data-theme="<id>"] block in theme.css with the new palette.
 */
import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';

export type ThemeId = 'parchment'; // extend union as new themes are added, e.g. | 'scifi'

export interface ThemeInfo {
  id: ThemeId;
  label: string;
  icon: string;
  description: string;
}

export const THEMES: ThemeInfo[] = [
  {
    id: 'parchment',
    label: 'Parchment',
    icon: '📜',
    description: 'Warm tavern parchment & candlelight',
  },
  // Future themes go here, e.g.:
  // { id: 'scifi', label: 'Cyberpunk', icon: '🤖', description: 'Neon grid / holographic UI' },
];

const STORAGE_KEY = 'tt-ui-theme';
const DEFAULT_THEME: ThemeId = 'parchment';

interface ThemeContextValue {
  theme: ThemeId;
  setTheme: (id: ThemeId) => void;
  themes: ThemeInfo[];
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: DEFAULT_THEME,
  setTheme: () => {},
  themes: THEMES,
});

function applyTheme(id: ThemeId) {
  document.documentElement.dataset.theme = id;
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<ThemeId>(() => {
    const stored = localStorage.getItem(STORAGE_KEY) as ThemeId | null;
    return stored && THEMES.some(t => t.id === stored) ? stored : DEFAULT_THEME;
  });

  // Apply on mount + whenever theme changes
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const setTheme = useCallback((id: ThemeId) => {
    setThemeState(id);
    localStorage.setItem(STORAGE_KEY, id);
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, setTheme, themes: THEMES }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
