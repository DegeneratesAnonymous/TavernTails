# Work Order

## Title
WO-013: Document Upload UI Polish (Retry, Progress, Thumbnails)

## Goal
Improve the document upload experience by adding upload progress indicators, retry flows for failed uploads, and thumbnail previews for uploaded files.

## Research Briefing
_See: Tech Lead Assessment 2026-03-06 — identified in PROGRESS.md "Immediate Next Steps" as outstanding polish item._

## Context
- `client/src/components/DocumentsPanel.tsx` currently supports file upload but lacks progress feedback, retry capability, and inline previews.
- Failed presigned uploads (S3 mode) give minimal feedback; users are left uncertain whether to retry.
- The backend already supports both direct upload (`/documents/{session}/upload`) and presign+register flow; the UI just needs polish around these existing endpoints.
- `server/agents/documents.py` is stable.

## Scope / Non-Goals
- **In scope:**
  - Upload progress bar / percentage indicator using `XMLHttpRequest` or `fetch` with `ReadableStream`
  - Retry button for failed uploads (track per-file state)
  - Thumbnail/icon preview for common file types (images: actual thumbnail; PDF/other: type icon)
  - Cancel in-progress upload
  - Clear error messaging distinguishing S3 failures from backend failures
- **Out of scope:**
  - Batch multi-file upload (single file at a time is fine for now)
  - Drag-and-drop (separate UX WO)
  - Backend changes

## Acceptance Criteria
- [ ] Upload shows a progress bar from 0–100%
- [ ] If upload fails, a "Retry" button appears alongside the error message
- [ ] Image files show a thumbnail preview after upload
- [ ] PDF files show a PDF icon; other files show a generic document icon
- [ ] Cancel button is available during upload
- [ ] Error message distinguishes network/S3 error from backend validation error
- [ ] Frontend tests cover: upload progress state, retry state, thumbnail rendering

## Implementation Notes
- **Files to modify:**
  - `client/src/components/DocumentsPanel.tsx` — main changes
  - `client/src/components/DocumentsPanel.test.tsx` — add/update tests
- **Pattern:** Track per-file state as `{ status: 'idle' | 'uploading' | 'success' | 'error', progress: number, error?: string }`
- **Progress tracking:** Use `XMLHttpRequest` with `progress` event for presign S3 uploads; use `onUploadProgress` if using axios, or implement streaming fetch for direct upload
- **Thumbnail:** For `File` with `type.startsWith('image/')`, use `URL.createObjectURL()` + `<img>` tag; clean up with `URL.revokeObjectURL()` on unmount

## Test Plan
- `npm test -- --watchAll=false --testPathPattern=DocumentsPanel`

## Rollback
- Revert `DocumentsPanel.tsx` to previous version
