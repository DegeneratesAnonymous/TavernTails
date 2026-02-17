# TavernTails Best Practices (Working Doc)

This project moves fast, but we keep quality high by using consistent best practices and doing small, verifiable changes.

Canonical references:
- `PROJECT_PLAN.md` (architecture/vision)
- `MVP_DELIVERY_CHECKLIST.md` (acceptance)
- `docs/CI_CHECKLIST.md` (quality gates)
- `docs/DEV_AGENTS.md` + `docs/dev-agents/*.md` (workflow)

## General Engineering
- Prefer PR-sized changes with a clear scope and acceptance criteria.
- Keep production behavior deterministic; avoid “works on my machine” state.
- Make failure modes actionable (good error messages, logs, and safe fallbacks).
- No ToS-violating integrations (e.g., do not scrape D&D Beyond). Prefer user-provided exports.

## Backend (FastAPI)
- Treat OpenAPI as a contract: routes should be discoverable and stable.
- Use explicit request/response models for JSON APIs when feasible.
- Prefer `Depends(get_current_user)` for any user-scoped data.
- Return consistent error shapes (`{"detail": ...}`) and appropriate HTTP status codes.
- Validate inputs early and fail fast with clear errors.
- Keep imports side-effect free where possible; avoid module-level network/IO.

### Files & Uploads
- Multipart uploads should accept `UploadFile` + `Form(...)` fields.
- Store provenance in `sheet.import` (source, timestamps, filename, extracted fields, overrides).
- Never set `Content-Type` manually for multipart requests from the browser.

## Frontend (React/TS)
- Prefer typed boundaries: narrow `any` at the edges, use typed helpers internally.
- Avoid silent failures: surface network errors and endpoint mismatches.
- Keep long-running async operations cancellable where practical.
- Don’t hardcode backend URLs in components; route through `api.ts`.

### Networking
- Use `apiFetch()` for authenticated calls.
- For `FormData` uploads, do not set a `Content-Type` header.
- On 401: prompt user/login or clear stale auth as needed.

## Testing & CI
- If behavior changes, add/adjust tests in the closest layer.
- Prefer targeted tests for new parsing logic (e.g., PDF widget extraction).
- Run `./ci.ps1` for CI-equivalent checks before merging.

## Security & Privacy
- Auth tokens: store and transmit via Authorization headers.
- Don’t log secrets or full raw exports in server logs.
- Principle of least privilege for storage providers and API keys.

## Account, Identity, and OAuth
- Always verify primary email before enabling critical actions (password change, provider unlink, data export).
- Provide password reset via short-lived, single-use tokens; rate-limit reset and verification endpoints.
- When linking providers (Google/Discord/Twitch), require recent login and show last-linked timestamps.
- Never allow unlinking the last remaining sign-in method (to avoid lockout).
- Store provider subject IDs (not emails) and keep minimal scope access.
- Log auth events (login, link, unlink, password change) without PII leakage.

## Retro Audits
When something feels flaky (e.g., refresh issues, 405s), do a short retro audit:
- Identify the *contract* (URL, method, payload, auth)
- Verify what’s running (ports, OpenAPI, health)
- Add guardrails (startup scripts, UX error messaging, tests)
