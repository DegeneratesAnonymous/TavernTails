# TavernTails — UI Design Guide

## Overview

TavernTails uses a **theme system** driven by CSS custom properties. The active theme is stored in `localStorage` under the key `tt-theme` and applied as a `data-theme` attribute on `<html>`. Theme variables cascade from `themes.css` into every component via the token names defined in `theme.css`.

The **default theme is Medieval** — dark, atmospheric, with gold accents and serif typography evoking candlelit tomes and ancient taverns.

---

## Theme System

### How It Works

```
App.tsx
  └─ ThemeProvider (contexts/ThemeContext.tsx)
       └─ sets data-theme on <html>
            └─ themes.css  ← [data-theme="medieval"] { --accent: #c8941a; ... }
                 └─ theme.css  ← body { background: var(--bg-color); ... }
                      └─ ui.css, component CSS  ← use var(--accent) etc.
```

### Adding a Theme Toggle

```tsx
import ThemeToggle from './components/ui/ThemeToggle'

// Drop anywhere in a toolbar:
<ThemeToggle />
```

### Reading or Setting the Theme in Code

```tsx
import { useTheme } from '../contexts/ThemeContext'

const { theme, setTheme } = useTheme()
setTheme('scifi')
```

---

## Available Themes

### ⚔️ Medieval *(default)*
> *Candlelit taverns, ancient tomes, blood and gold.*

| Token | Value |
|---|---|
| `--bg-color` | `#0d0805` |
| `--surface` | `#1e1208` |
| `--accent` | `#c8941a` (gold) |
| `--accent-secondary` | `#8b1a1a` (crimson) |
| `--text` | `#f4e9c9` (parchment) |
| `--highlight` | `#f0c040` |
| `--radius` | `3px` (sharp, chiseled) |
| `--font-heading` | Cinzel Decorative → Cinzel → serif |
| `--font-ui` | Cinzel → serif |
| `--font-body` | IM Fell English → serif |

**Character:** Sharp corners, small radius. Uppercase Cinzel labels. Gold borders. Crimson destructive actions. Ambient radial gold/crimson glows on the background. **Cards are parchment vellum** (`#ede5c4 → #ccb37e`) — ink-dark text on aged paper panels, floating on a dark candlelit wood/stone background. Auth card uses slightly lighter/fresher parchment (`#fef4d4 → #eadcb0`).

---

### 🚀 Sci-Fi
> *Deep-space neon, circuit glow, void silence.*

| Token | Value |
|---|---|
| `--bg-color` | `#000814` |
| `--surface` | `#001233` |
| `--accent` | `#00b4d8` (cyan) |
| `--accent-secondary` | `#7209b7` (violet) |
| `--text` | `#caf0f8` |
| `--radius` | `4px` |
| `--font-heading` | Orbitron → Exo 2 → sans-serif |
| `--font-ui` | Exo 2 → Rajdhani → sans-serif |
| `--font-mono` | Share Tech Mono |

**Character:** Cyan/violet palette. Uppercase tight-tracked labels. Neon glow borders. Grid lines more visible.

---

### 🖖 Star Trek
> *LCARS panels, starship orange, Federation precision.*

| Token | Value |
|---|---|
| `--bg-color` | `#000000` |
| `--surface` | `#160820` |
| `--accent` | `#ff9900` (LCARS orange) |
| `--accent-secondary` | `#cc6699` (coral) |
| `--text` | `#f0e6ff` |
| `--radius` | `0px` (hard 90° corners) |
| `--font-heading` | Antonio → Rajdhani → sans-serif |
| `--font-ui` | Antonio → sans-serif |

**Character:** Zero border-radius everywhere. LCARS-style thick left border on cards. Bold orange headings. Hard panel lines.

---

### ◻ Neutral *(former default)*
> *Clean dark baseline — familiar, no-frills.*

| Token | Value |
|---|---|
| `--bg-color` | `#332A21` |
| `--surface` | `#2E4A52` |
| `--accent` | `#E09A4F` |
| `--accent-secondary` | `#AD885F` |
| `--text` | `#ffffff` |
| `--radius` | `12px` (soft rounded) |
| `--font-*` | system-ui |

**Character:** Soft rounded corners. System fonts. Warm brown-teal palette. Same as previous TavernTails default styling.

---

## CSS Token Reference

All tokens below are defined per-theme in `src/themes.css` and used globally.

| Token | Purpose |
|---|---|
| `--bg-color` | Page background fill |
| `--grid-color` | Background grid line color |
| `--surface` | Card / panel background |
| `--surface-dark` | Topbar, drawer, modal backgrounds |
| `--surface-muted` | Muted / subdued panel |
| `--surface-neutral` | Neutral mid-tone surface |
| `--muted-surface` | Secondary muted surface |
| `--accent` | Primary CTA, active states, gold/cyan/orange |
| `--accent-secondary` | Secondary actions, destructive hint |
| `--text` | Primary text color |
| `--muted-text` | Secondary / helper text |
| `--error` | Error states |
| `--highlight` | Hover glow, active tab underline |
| `--radius` | Border-radius used everywhere |
| `--shadow-1` | Standard card/panel shadow |
| `--tt-border` | Default border color |
| `--tt-border-strong` | Emphasized border (focus, hover) |
| `--tt-focus` | Focus ring color |
| `--tt-surface-2` | Nested surface / sub-card |
| `--font-heading` | Display headings (h1, h2) |
| `--font-ui` | Labels, buttons, nav |
| `--font-body` | Body copy, descriptions |
| `--font-mono` | Code blocks |
| `--bg-radial-1/2/3` | Ambient background gradient layers |

---

## Button Styles

All buttons use the `.btn` base class. Color is inherited from CSS token vars.

| Class | Background | Text | Use |
|---|---|---|---|
| `.btn` | `--accent` | `--text` | Primary CTA |
| `.btn-secondary` | `--accent-secondary` | `--text` | Secondary action |
| `.btn-quiet` | `rgba(surface, 0.35)` | `--text` | Low-emphasis |
| `.btn-ghost` | transparent | `--text` | Ghost / outline |
| `.btn-danger` | red-tinted | white | Destructive |
| `.btn-sm` | — | — | Compact size modifier |
| `.btn-icon-only` | — | — | Icon-only, square |

- Hover: `translateY(-1px)` + border brightens
- Focus: 3px ring in `--tt-focus`
- Font: `var(--font-ui)` — inherits theme typography
- Radius: `var(--radius)` — 0px in Star Trek, 3px in Medieval, 12px in Neutral

---

## Card Style

Cards use the `.card` utility class. Each theme overrides card appearance:

- **Medieval**: Parchment vellum surface `#ede5c4 → #ccb37e`, dark ink text `#1c0d03`, brown leather border — ink on aged paper floating on dark wood background
- **Sci-Fi**: Dark navy `#001233`, cyan border glow
- **Star Trek**: Nearly-black `#0d0020`, thick orange left border, 0px radius
- **Neutral**: Teal-dark `#2E4A52`, subtle white border

---

## Typography Rules

- Heading elements (`h1`–`h3`) and `.page-title`, `.section-title`, `.topbar-brand` use `var(--font-ui)` per theme
- Body text uses `var(--font-body)`
- Code/mono uses `var(--font-mono)`
- In **Medieval**, button and heading text is `text-transform: uppercase` with `letter-spacing: 0.06–0.12em`
- In **Star Trek**, all labels are uppercase with `letter-spacing: 0.15em`
- In **Neutral**, no text-transform is applied

---

## Accessibility

- All themes maintain ≥4.5:1 contrast between `--text` and `--surface`
- Focus rings use `--tt-focus` — visible against all theme backgrounds
- Reduced-motion: `@media (prefers-reduced-motion)` strips transitions/animations globally
- ThemeToggle uses `aria-label` with current theme name

---

## Adding a New Theme

1. Add an entry to `THEMES` in `src/contexts/ThemeContext.tsx`
2. Add a `[data-theme="your-theme"]` block to `src/themes.css` defining all required tokens
3. Load any required Google Fonts in `public/index.html`
4. Optionally add card/button overrides scoped to `[data-theme="your-theme"] .card { ... }`

---

## Particle & Ambient Effects

Theme-specific ambient particles provide atmospheric depth. They are managed by two components and a shared intensity context.

### Components

| Component | Theme | Description |
|---|---|---|
| `EmberParticles` | `medieval` | Gold embers that float up from the bottom of the viewport |
| `StarParticles` | `scifi` | Slow, subtle twinkling starfield across the full background |

Both are rendered in `App.tsx` (or the root layout) and produce no DOM when their theme is not active.

### CSS Classes

| Class | Purpose |
|---|---|
| `.tt-ember-container` | Fixed full-viewport container for ember particles |
| `.tt-ember` | Individual ember dot; driven by `@keyframes tt-ember-rise` |
| `.tt-star-container` | Fixed full-viewport container for star particles |
| `.tt-star` | Twinkling star; driven by `@keyframes tt-star-twinkle` |
| `.tt-star--static` | Non-animated star (static opacity) |

### CSS Variables (per-particle)

| Variable | Used by | Purpose |
|---|---|---|
| `--star-min` | `.tt-star` | Minimum opacity at the dim end of the twinkle cycle |
| `--star-max` | `.tt-star` | Peak opacity at the bright end of the twinkle cycle |
| `--ember-max` | `.tt-ember` | Peak opacity for the ember rise animation |

### Intensity System

Both particle components respond to `ParticleContext`. Intensity is a normalized `0–1` value:

- **`0` (resting)** — Embers sparse and dim; stars barely visible.
- **`1` (peak)** — Embers dense, bright, larger; stars fully bright.

#### Hooks

```tsx
import { useParticles } from '../contexts/ParticleContext'
import { useParticleIntensity } from '../contexts/ParticleContext'

// Manual control
const { setIntensity } = useParticles()
useEffect(() => { setIntensity(completedSteps / totalSteps) }, [completedSteps])

// Convenience: sets while mounted, resets to 0 on unmount
useParticleIntensity(completedSteps / totalSteps, [completedSteps])
```

#### When to wire intensity

Use `useParticleIntensity` whenever a page or flow has measurable progress:
- Form completion (fields filled / total fields)
- Multi-step wizards (current step / total steps)
- Loading sequences (bytes loaded or tasks completed)
- Campaign/session creation flows

---

## Reusable UI Decorative Elements

The following CSS classes in `ui.css` are intended to be used consistently across all pages and themes:

| Class | Purpose | Usage |
|---|---|---|
| `.tt-divider` + `.tt-divider-line` + `.tt-divider-gem` | Themed ornamental horizontal divider with a diamond gem | Section separators in cards and modals |
| `.tt-rune-bar` | Uppercase, wide letter-spacing label in accent color | Sub-section labels, decorative headings |
| `.tt-card-ornament-tl` | Top-left corner ornament glyph (requires `position:relative` parent) | Decorative card corners in medieval theme |
| `.tt-card-ornament-br` | Bottom-right corner ornament glyph | Paired with `.tt-card-ornament-tl` |
| `.empty-state` | Dashed bordered placeholder for empty lists/sections | Zero-state panels |
| `.segmented` | Tab-like segmented control | View mode toggles (e.g., Grid / List) |
| `.page-header` + `.page-title` + `.page-subtitle` | Standard page header layout | Top of every main content page |

### Recommended usage pattern (medieval)

```tsx
<div className="card card-pad" style={{ position: 'relative' }}>
  <span className="tt-card-ornament-tl">✦</span>
  <h2 className="section-title">Section</h2>
  <div className="tt-divider">
    <div className="tt-divider-line" />
    <div className="tt-divider-gem" />
    <div className="tt-divider-line" />
  </div>
  {/* content */}
  <span className="tt-card-ornament-br">✦</span>
</div>
```
