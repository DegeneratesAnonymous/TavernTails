# UI Design Guide

## Color Palette
Use the palette below as the source of truth for UI styling.

- #332A21 — Base background
- #2B3336 — Dark surface
- #5F808B — Primary surface
- #7A6C5C — Secondary surface
- #AD885F — Warm surface accent
- #E09A4F — Primary action / destructive emphasis
- #AD885F — Focus / selection / info
- #525D61 — Neutral border
- #47423D — Muted panel

## Usage Guidelines
- Base background: #332A21
- Primary surfaces (cards, panels): #5F808B
- Secondary surfaces (sub-cards, highlights): #7A6C5C
- Warm surface accent: #AD885F
- Primary actions + destructive actions: #E09A4F
- Selection/focus states: #AD885F

## Button Styles
- Primary button: background #E09A4F, text #332A21, border transparent.
- Secondary button: background #AD885F, text #332A21, border transparent.
- Quiet button: background rgba(95, 128, 139, 0.35), text #ffffff, border #525D61.
- Destructive button: background #E09A4F, text #332A21, optional icon.
- Icon-only button: use .btn-icon-only with a 16px icon, no text.
- Tooltips: icon-only buttons must include title + aria-label for clarity.
- Hover: increase brightness by ~8–12% and keep text legible.
- Focus: 3px ring in rgba(173, 136, 95, 0.25).

## Accessibility
- Ensure text contrast is readable on all surfaces.
- Use muted focus rings; avoid high-chroma cyan.

## Notes
- Keep button text legible; prefer near-black text on bright action colors and near-white text on dark surfaces.
