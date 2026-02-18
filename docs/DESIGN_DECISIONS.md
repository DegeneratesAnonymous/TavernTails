Design Decisions
================

Purpose
-------
Record design proposals, options, and decisions so the team (and agents) can proceed without repeated granular approvals.

Decision Rules (what the agents will do by default)
---------------------------------------------------
- Default autonomy: implement changes that follow `PROJECT_PLAN.md` and `docs/dev-agents/*` without asking the captain.
- Agents will ask the user when a change:
  - alters gameplay loops, UX, or core features;
  - changes public API/WS contracts or data schemas;
  - affects security, auth, or RBAC behavior;
  - touches multiple subsystems or is large in scope;
  - reaches QA escalation (WO `loop_count` >= 3) or is a security/data-loss finding.
- When asking, agents present 2–3 concise options, tradeoffs, and a recommended choice.

Decision Template
-----------------
Use this template for new proposals. Add one file per proposal under `docs/design-decisions/` when ready.

- Title: Short descriptive name
- Author: Who proposed it
- Date: YYYY-MM-DD
- Summary: One-paragraph description of the change
- Context: Why this is needed; links to `PROJECT_PLAN.md` or WOs
- Options: List 2–3 alternatives (A/B/C), each with:
  - Description
  - Pros
  - Cons
  - Estimated effort (S/M/L)
- Recommendation: Which option the proposer recommends and why
- Acceptance Criteria: Concrete checks/tests required to consider this done
- Dependencies: Any infra, data, or other tasks required
- Risk / Rollback Plan: How to revert or mitigate if things go wrong
- Decision: (leave blank until a captain/PM approves)
  - Approved Option: A/B/C
  - Decision By: @username
  - Date: YYYY-MM-DD
  - Notes: Any follow-ups or partial approvals

Process
-------
- Draft: Agent or contributor writes a proposal using the template and places it in `docs/design-decisions/` or links it from a WO.
- Review: Tech Lead reviews; if minor and within plan, Tech Lead may approve and implement. If not, it goes to the Captain (you) for final approval.
- Implement: Implementation must reference the decision (WO/PR) and include acceptance criteria and tests.
- Close: After meeting acceptance criteria and passing QA, record the final state in the decision file and link PR/WOs.

Example (brief)
---------------
- Title: Use session-scoped suggestion tuning
- Summary: Allow suggestions endpoint to accept a `theme_hint` query param to bias results.
- Options:
  - A: Add `theme_hint` param (low effort). Pros: quick, targeted. Cons: minor API change.
  - B: Add server-side ML ranking (large effort). Pros: better results. Cons: high complexity.
  - C: Keep current behavior (do nothing).
- Recommendation: A
- Acceptance Criteria: API accepts param, tests cover default and hinted behavior, docs updated.

Where to put files
------------------
- Draft decisions: `docs/design-decisions/drafts/`
- Approved/active decisions: `docs/design-decisions/approved/`

Notes
-----
This document codifies the captain-agent workflow: agents implement tactical work guided by the plans and only escalate strategic design questions. Keep proposals short and focused — decisions should be easy to review.