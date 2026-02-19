# Repository Settings

This document captures the recommended GitHub repository settings for TavernTails.

> **Note:** Branch protection rules and most settings below must be applied manually by a repository admin via **Settings** in the GitHub UI.

## Branch Protection – `main`

Navigate to **Settings → Branches → Add branch protection rule** for `main`.

| Setting | Recommended Value |
|---------|------------------|
| Require a pull request before merging | ✅ Enabled |
| → Required approvals | 1 (minimum) |
| → Dismiss stale pull request approvals when new commits are pushed | ✅ Enabled |
| Require status checks to pass before merging | ✅ Enabled |
| → Required checks | `backend`, `frontend` (CI jobs) |
| Require branches to be up to date before merging | ✅ Enabled |
| Require conversation resolution before merging | ✅ Enabled |
| Include administrators | ✅ Enabled |
| Allow force pushes | ❌ Disabled |
| Allow deletions | ❌ Disabled |

## Branch Protection – `develop` (if used)

Apply the same rules as `main`, but with:
- Required approvals: 1
- Allow force pushes: ❌ Disabled

## Security Settings

Navigate to **Settings → Security & analysis**:

| Feature | Recommendation |
|---------|---------------|
| Dependency graph | ✅ Enable |
| Dependabot alerts | ✅ Enable |
| Dependabot security updates | ✅ Enable |
| Secret scanning | ✅ Enable (push protection recommended) |
| Code scanning (CodeQL) | ✅ Enable when capacity allows |

### Secret Scanning Push Protection

Prevents secrets from being committed to the repository. Enable under **Settings → Security & analysis → Push protection**.

See [`docs/SECRET_MANAGEMENT.md`](SECRET_MANAGEMENT.md) for guidelines on managing secrets.

## Collaborator Management

Navigate to **Settings → Collaborators and teams**:

- Add contributors with **Write** access.
- Add trusted reviewers/maintainers with **Maintain** access.
- Reserve **Admin** access to project owners only.
- Use Teams (in the organization) to manage access at scale.

## General Settings

Navigate to **Settings → General**:

| Setting | Recommendation |
|---------|---------------|
| Default branch | `main` |
| Allow merge commits | ✅ (squash preferred for cleaner history) |
| Allow squash merging | ✅ Enable – default for PRs |
| Allow rebase merging | ✅ Enable (optional) |
| Automatically delete head branches | ✅ Enable |
| Issues | ✅ Enable |
| Projects | ✅ Enable |
| Discussions | Optional (enable if community Q&A is desired) |

## Webhooks (Future)

When a deployment pipeline or external CI system is added, configure webhooks under **Settings → Webhooks**. Document secrets in the team password manager (see `docs/SECRET_MANAGEMENT.md`).

## References

- [docs/CI_CHECKLIST.md](CI_CHECKLIST.md) – quality gates enforced by branch protection
- [docs/CONTRIBUTING.md](CONTRIBUTING.md) – contributor workflow
- [docs/SECRET_MANAGEMENT.md](SECRET_MANAGEMENT.md) – secret management guidelines
