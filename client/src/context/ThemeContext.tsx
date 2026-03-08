/**
 * ThemeContext — global theme selection + persistence.
 *
 * Usage:
 *   const { theme, setTheme, themes } = useTheme();
 *
 * Adding a new theme: see src/themes/_template.css and src/themes/index.ts.
 */
import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { THEMES, DEFAULT_THEME } from '../themes/index';
import type { ThemeId, ThemeInfo } from '../themes/index';
export type { ThemeId, ThemeInfo } from '../themes/index';
export { THEMES };

const STORAGE_KEY = 'tt-ui-theme';

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
