/**
 * TavernTails Theme Registry
 * ──────────────────────────
 * Add a new theme:
 *   1. Copy  _template.css  →  <id>.css  and fill in all variables.
 *   2. Import the new CSS at the bottom of this file.
 *   3. Add an entry to the THEMES array below.
 *   4. Import the CSS in theme.css: @import './themes/<id>.css';
 *
 * The ThemeSelector UI in the top bar is built automatically from THEMES.
 */

// ── CSS imports — one per theme file ─────────────────────────────────────────
import './parchment.css';
// import './scifi.css';   // ← uncomment when ready

// ── Theme metadata ────────────────────────────────────────────────────────────
export type ThemeId = 'parchment';
// Extend the union as new themes are added: | 'scifi' | 'highcontrast'

export interface ThemeInfo {
  id: ThemeId;
  /** Display label in the ThemeSelector dropdown */
  label: string;
  /** Emoji icon shown in the dropdown and trigger button */
  icon: string;
  /** One-line description shown below the label */
  description: string;
}

export const THEMES: ThemeInfo[] = [
  {
    id: 'parchment',
    label: 'Parchment',
    icon: '📜',
    description: 'Warm candlelight tavern — gold accents & dark wood',
  },
  // {
  //   id: 'scifi',
  //   label: 'Cyberpunk',
  //   icon: '🤖',
  //   description: 'Neon grid — cyan & magenta holographic UI',
  // },
];

export const DEFAULT_THEME: ThemeId = 'parchment';
