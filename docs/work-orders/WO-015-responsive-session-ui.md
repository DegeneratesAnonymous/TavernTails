# Work Order

## Title
WO-015: Responsive Session UI & Mobile Layout Polish

## Goal
Make the session gameplay UI usable on tablet and mobile screens by implementing responsive layouts for the GameplayLayout, chat panel, and character panel components.

## Research Briefing
_See: Tech Lead Assessment 2026-03-06 — responsive layout identified as Phase 1 quality requirement._

## Context
- `client/src/components/GameplayLayout.tsx` uses a fixed multi-column layout (drawer + main + suggestions rail) that breaks on screens below 1024px wide.
- The target personas include players on tablets (solo adventurers on the couch) and async parties on mobile.
- `PROJECT_PLAN.md §18` describes the session UI architecture but does not specify responsive breakpoints.
- Current CSS uses hardcoded pixel widths; no media queries or responsive grid/flex.

## Scope / Non-Goals
- **In scope:**
  - Mobile-first responsive breakpoints for GameplayLayout (≤768px: single column, drawer becomes bottom sheet)
  - Chat panel readable and usable on mobile (full-width, input at bottom)
  - Character panel usable on tablet (collapsible sidebar on 768–1024px)
  - Suggestions rail: hidden on mobile, accessible via floating action button
  - Turn tracker: compact view on small screens
- **Out of scope:**
  - Native mobile app (PWA can be addressed separately)
  - Redesign of desktop layout
  - Backend changes

## Acceptance Criteria
- [ ] At 375px width (iPhone SE): single-column view, chat is primary focus, character/suggestions accessible via buttons
- [ ] At 768px width (iPad portrait): two-column layout works without overflow
- [ ] At 1024px+ (desktop): existing layout unchanged
- [ ] No horizontal scrollbars at any breakpoint
- [ ] Touch targets ≥44px on mobile
- [ ] Tests: snapshot/visual regression tests for responsive breakpoints (or manual screenshot verification)
- [ ] `docs/DESIGN_GUIDE.md` updated with responsive breakpoints

## Implementation Notes
- **Files to modify:**
  - `client/src/components/GameplayLayout.tsx` + its CSS module
  - `client/src/components/chat/Chat.tsx` + CSS
  - `client/src/components/CharacterPanel.tsx` + CSS
  - `client/src/components/NarrativeView.tsx` + CSS
  - `docs/DESIGN_GUIDE.md`
- **Breakpoints (align with standard):**
  - Mobile: `max-width: 767px`
  - Tablet: `768px–1023px`
  - Desktop: `1024px+`
- **Drawer strategy:** At mobile, drawer becomes a `position: fixed` bottom sheet with overlay; toggle via hamburger/FAB button
- **CSS approach:** Extend existing CSS modules with `@media` queries; avoid new CSS framework dependency

## Test Plan
- `npm test -- --watchAll=false --testPathPattern=GameplayLayout`
- Manual: Chrome DevTools device emulation at 375px, 768px, 1280px

## Rollback
- Revert CSS module changes; GameplayLayout structure is unchanged
