# Secret Management & Key Rotation SOP

_Last updated: 2025-12-08_

This document defines where TavernTAIls secrets live, how they are rotated, and the runbooks for keeping development, CI, and production credentials in sync. It satisfies Project Plan §17 action item “Schedule key rotations and document secret management SOP.”

## 1. Secret Inventory
| Secret | Purpose | Environments | Storage Location |
| --- | --- | --- | --- |
| `TAVERNTAILS_SECRET` | JWT signing key for access tokens | dev / staging / prod | `.env` (dev), platform secret store (staging/prod), GitHub Actions secret `TAVERNTAILS_SECRET` |
| `TAVERNTAILS_DATABASE_URL` | Database DSN containing creds | staging / prod | Secret store entry per environment + GitHub Actions secret `DATABASE_URL` |
| AWS `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Access to S3 bucket for document storage | staging / prod (when `TAVERNTAILS_STORAGE_MODE=s3`) | IAM user with least privilege; secrets in AWS Secrets Manager or deployment platform |
| `EMAIL_SMTP_PASSWORD` (or provider token) | Transactional email / invite delivery | staging / prod | Secret manager entry + GitHub Actions secret when CI needs it |
| `OPENAI_API_KEY` / `STABILITY_API_KEY` (future) | AI model access | staging / prod | Secret manager entry + GitHub Actions secret |
| GitHub Deploy Key / SSH key | Push/pull automation for infra repos | CI only | GitHub Secrets (`DEPLOY_KEY`) + developer password manager |

> _Local development_ seeds `test@example.com / secret` and lives entirely inside the developer’s machine. Production/staging secrets must **never** be checked into git.

## 2. Rotation Cadence
| Secret | Cadence | Owner | Notes |
| --- | --- | --- | --- |
| JWT signing key (`TAVERNTAILS_SECRET`) | Every 30 days or immediately after any auth incident | Backend lead | Generate 32-byte random string. Rotation invalidates existing sessions; announce maintenance window (see §3.1).
| AWS access keys | Every 90 days | Infra/DevOps | Use IAM access key rotation: create new key, update secrets, deactivate old key after verification.
| Database password / connection string | Quarterly, or when DB user permissions change | Infra/DBA | Rotate managed DB credentials using provider tooling; update `TAVERNTAILS_DATABASE_URL` and redeploy services.
| Email / AI provider tokens | Follow provider policy (30–60 days) | Feature owner | Store in password manager and mirror into platform secret store; revoke old token after rollout.
| GitHub Actions secrets / deploy key | Align with JWT cadence or whenever automation scope changes | Repo maintainer | Re-encrypt secrets through GitHub UI; keep encrypted backup in password manager only.

Create two calendar reminders (“TavernTAIls key rotation”) for the first business Monday of each month (JWT) and the first business Monday of each quarter (AWS/DB). The calendar invite should include links to this SOP and the rotation checklists below.

## 3. Rotation Runbooks

### 3.1 JWT Signing Key
1. Generate a new key: `python - <<'PY'\nimport secrets; print(secrets.token_urlsafe(48))\nPY`.
2. Update `.env` locally (`TAVERNTAILS_SECRET=<new>`) and redeploy non-prod environments.
3. Update GitHub Actions secret `TAVERNTAILS_SECRET` so CI uses the same value for smoke tests.
4. Schedule a short production maintenance window (clients must re-authenticate). Deploy with the new secret.
5. Verify new logins succeed; old tokens should be rejected with 401.
6. Destroy the previous secret everywhere it was stored.

### 3.2 AWS Access Keys (S3 document store)
1. In AWS IAM, create a second access key for the `taverntails-s3-uploader` IAM user.
2. Update deployment platform variables + GitHub Actions secrets (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`).
3. Redeploy staging ➜ run `venv\Scripts\python.exe -m pytest server/tests/test_presign_register.py -q` locally to confirm presign/register still succeeds.
4. Once prod confirms uploads, deactivate the old access key and update password managers.

### 3.3 Database Credentials
1. Use managed DB console (or `ALTER ROLE ... PASSWORD ...`) to issue a new password for the `taverntails_app` user.
2. Update the connection string wherever `TAVERNTAILS_DATABASE_URL` is stored.
3. Run `alembic upgrade head` and `pytest server/tests -q` to confirm migrations/tests still pass with the new DSN.
4. Remove the old password and purge connection pools.

### 3.4 Email / AI Provider Tokens
1. Generate a new API token in the provider dashboard.
2. Update platform secrets and GitHub Actions secrets if CI requires them.
3. Redeploy and send a smoke request (e.g., trigger invite email or sample AI narration) to validate.
4. Revoke the old token.

## 4. Storage & Tooling Guidelines
- **Local `.env`:** keep developer secrets in a per-user `.env` (already gitignored). Sample values live in `.env.example` (add if missing) without real credentials.
- **Password Manager:** store master copies of production secrets in the team password manager (1Password/Bitwarden). Reference entries in calendar reminders.
- **Secret Scanner:** run `trufflehog filesystem --since-commit=<last-release>` before releases to verify no plaintext secrets exist.
- **CI/CD:** all secrets used by GitHub Actions must be added via the repository **Settings → Secrets and variables** UI and never via plaintext workflow files.

## 5. Incident Response Hooks
1. **If a secret leaks** (e.g., from logs or Git history): immediately revoke it, rotate per the relevant runbook, and open an incident issue summarizing the scope.
2. **If AWS reports compromised key:** disable the key, rotate bucket policy, re-run `pytest server/tests/test_presign_register.py -q` to ensure no regressions.
3. **Audit trail:** update `PROGRESS.md` with date + command(s) used during rotation for future handoffs.

## 6. Verification Checklist
- [ ] `.env` files excluded from git (`.gitignore`).
- [ ] Current secrets documented in password manager entries.
- [ ] Calendar reminders confirmed for monthly (JWT) and quarterly (AWS/DB) rotation.
- [ ] Most recent rotation logged in `PROGRESS.md` Validation Log.

Keeping this SOP current is a release gate; update the “Last updated” stamp with every modification.
