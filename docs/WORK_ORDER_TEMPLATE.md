# Work Order

## Title

## Goal
One sentence: what “done” looks like.
## Research Briefing (Research Agent)
> Invoke the Research Agent with the questions below *before* the Tech Lead plans execution.
> Replace this block with the Research Briefing output once received.

Research questions for this Work Order:
- (add specific questions here — e.g. external spec, PDF format, community parsers, licensing)
## Context
- Why this is needed
- What’s already implemented

## Scope / Non-Goals
- In scope:
- Explicitly out of scope:

## Acceptance Criteria
- [ ] …
- [ ] …
- [ ] Tests pass

## Implementation Notes
- Suggested files / modules:
- API endpoints affected:
- WebSocket events affected:

## Test Plan
- Backend: `venv\Scripts\python.exe -m pytest server/tests -q` (or narrower)
- Frontend: `cd client; npm test -- --watchAll=false` (or `npm run build`)

## Rollback
How to revert safely if needed.
