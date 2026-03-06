# Work Order

## Title
WO-010: Campaign Invite System

## Goal
Allow campaign hosts to invite other players via shareable tokens so that multi-player campaigns can be joined without requiring admin intervention.

## Research Briefing
_See: Tech Lead Assessment 2026-03-06 — Phase 1 priority._

## Context
- Currently all campaigns are strictly single-owner; there is no mechanism for players to join an existing campaign.
- The PROJECT_PLAN.md §Phase 1 lists "invite system with character assignment" as the first post-MVP deliverable.
- `server/agents/campaigns.py` owns campaign CRUD and `server/db.py` has the campaign model; character assignment exists but is not linked to campaign membership.

## Scope / Non-Goals
- **In scope:**
  - `POST /campaigns/{id}/invites` — generate a short-lived invite token (e.g. 7-day expiry)
  - `GET /invites/{token}` — look up campaign info by token (unauthenticated, returns campaign name + host)
  - `POST /invites/{token}/accept` — authenticated user joins campaign as a `member`
  - `GET /campaigns/{id}/members` — list current members (host-only)
  - `DELETE /campaigns/{id}/members/{uid}` — remove member (host-only)
  - Basic UI: "Invite Players" button in campaign settings, link copy, accept-invite landing page
- **Out of scope:**
  - Email delivery of invites (link-copy-only for MVP)
  - Role escalation beyond `member` vs `host`
  - Transfer of campaign ownership

## Acceptance Criteria
- [ ] Host can create an invite token via the API and get a shareable URL
- [ ] Non-authenticated user can preview campaign info via invite URL
- [ ] Authenticated user can accept an invite and is added as a campaign member
- [ ] Campaign member list is visible to the host
- [ ] Host can remove a member
- [ ] All endpoints protected correctly (only host can manage invites/members)
- [ ] Tokens expire after 7 days
- [ ] Tests cover: create invite, accept invite, duplicate accept, expired token, member removal
- [ ] Frontend: "Invite" button in campaign settings + accept-invite page

## Implementation Notes
- **Backend files:**
  - `server/agents/campaigns.py` — add invite/member router endpoints
  - `server/db.py` — add `CampaignInvite` and `CampaignMember` models + migrations
  - `server/tests/test_campaign_invites.py` — new test file
- **Frontend files:**
  - `client/src/components/dashboard/CampaignSettings.tsx` — add invite section
  - `client/src/components/AcceptInvite.tsx` — new invite acceptance page
  - `client/src/App.tsx` — route `/invite/:token`
- **Alembic:** New migration for `campaign_invites` and `campaign_members` tables
- **DB schema:**
  ```
  campaign_invites: id, campaign_id, token (UUID), created_by, expires_at, used_count
  campaign_members: id, campaign_id, user_id, joined_at, role ('member'|'host')
  ```
- **Auth:** Invite creation requires `require_auth` + host check; accept requires `require_auth`; preview is public

## Test Plan
- Backend: `python -m pytest server/tests/test_campaign_invites.py -q`
- Frontend: `npm test -- --watchAll=false --testPathPattern=AcceptInvite`

## Rollback
- Remove invite/member endpoints from campaigns router
- Drop migration (alembic downgrade)
- Remove frontend invite components
