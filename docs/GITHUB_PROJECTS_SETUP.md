# GitHub Projects Setup

This document provides step-by-step instructions for creating and configuring the **TavernTails MVP** project board on GitHub.

> **Note:** Project boards must be set up manually via the GitHub UI. The instructions below reflect the recommended configuration.

## 1. Create the Project

1. Navigate to the repository on GitHub.
2. Click the **Projects** tab → **New project**.
3. Select **Board** layout.
4. Name the project: **TavernTails MVP**.
5. Add a description: _Tracks MVP delivery across all work packages (see PROJECT_PLAN.md §12)_.

## 2. Recommended Columns

| Column | Purpose |
|--------|---------|
| **Backlog** | All triaged issues not yet scheduled |
| **To Do** | Issues committed to the current sprint/iteration |
| **In Progress** | Issues actively being worked on |
| **In Review** | PRs opened; awaiting code review |
| **Testing** | Changes merged; awaiting QA sign-off |
| **Done** | Accepted and closed |

## 3. Automation Rules

Configure the following built-in automations (Settings → Workflows):

| Trigger | Action |
|---------|--------|
| Issue opened | Move to **Backlog** |
| PR opened | Move linked issue to **In Review** |
| PR merged | Move linked issue to **Testing** |
| Issue closed | Move to **Done** |

## 4. Linking Issues to the Project

### Automatically
- Any issue opened in the repository will be moved to **Backlog** once the automation above is enabled.

### Manually
1. Open an issue.
2. In the right-hand sidebar, click **Projects** → select **TavernTails MVP**.
3. Set the **Status** field to the appropriate column.

## 5. Work Package Views

Consider adding filtered views (grouped by label) for each work package:

- Filter: `label:"WP#1: auth"` → View: **WP#1 Auth**
- Filter: `label:"WP#2: campaigns"` → View: **WP#2 Campaigns**
- Repeat for WP#3–WP#9

## 6. Milestones (Recommended)

Create milestones to track release goals:

| Milestone | Target |
|-----------|--------|
| `MVP Alpha` | Core auth, campaigns, characters working end-to-end |
| `MVP Beta` | Agent orchestration, dice, documents, chat |
| `MVP Release` | Image agent, CI gates, full test coverage |

Milestones are created under **Issues → Milestones → New milestone**.

## References

- [PROJECT_PLAN.md](../PROJECT_PLAN.md) – canonical architecture and work packages
- [MVP_DELIVERY_CHECKLIST.md](../MVP_DELIVERY_CHECKLIST.md) – MVP acceptance criteria
- [docs/LABELS.md](LABELS.md) – full label reference
