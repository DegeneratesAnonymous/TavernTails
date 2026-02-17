# CI/CD Checklist and Quality Gates

This document defines the Continuous Integration (CI) quality gates for TavernTAIls, including what checks must pass before merging code to `main` and guidance on when to block merges.

## Local One-Command Runner (Windows-safe)

If your workspace path contains special characters like `&` (common under OneDrive), some `npm` scripts may fail on Windows due to `.bin` path quoting. Use the repo root runner instead:

- `./ci.ps1`

It runs backend + frontend checks using explicit `node` entrypoints and works reliably in `Dungeons&Dragons`-style paths.

## CI Pipeline Overview

Our CI pipeline runs automatically on every pull request and push to `main`. It consists of two primary jobs (backend and frontend) plus an optional smoke test job.

### CI Workflow Trigger

- **Pull Requests** to `main` branch
- **Direct Pushes** to `main` branch

### Required Jobs

All jobs must pass (green ✓) before merging unless explicitly bypassed by maintainer.

## Backend Quality Gates (Python)

### Job: `backend`

**Environment**: 
- Ubuntu latest
- Python 3.11 (primary), Python 3.12 (compatibility)

**Required Steps**:

#### 1. Linting (Ruff)
**Purpose**: Enforce code style and catch common errors
**Command**: `ruff check server/`
**Blocking**: ✅ Yes - must pass

**Common Issues**:
- Unused imports
- Line too long (>120 chars)
- Missing docstrings
- Undefined names

**How to Fix Locally**:
```bash
pip install ruff
ruff check server/
ruff check server/ --fix  # Auto-fix some issues
```

#### 2. Type Checking (mypy)
**Purpose**: Catch type errors before runtime
**Command**: `mypy server/ --ignore-missing-imports --check-untyped-defs`
**Blocking**: ⚠️ Non-blocking initially (will be blocking once codebase is typed)

**Common Issues**:
- Missing type hints
- Incompatible types in assignments
- Missing return types
- Any types (use specific types)

**How to Fix Locally**:
```bash
pip install mypy
mypy server/ --ignore-missing-imports --check-untyped-defs
```

**Note**: Currently set to `continue-on-error: true` in CI to allow gradual adoption of type hints. Will be made blocking once core modules are properly typed.

#### 3. Unit Tests (pytest)
**Purpose**: Ensure functionality works as expected
**Command**: `pytest server/tests -v --cov=server --cov-report=term`
**Blocking**: ✅ Yes - must pass

**Coverage Requirements**:
- Minimum: 70% overall coverage (aspirational)
- New code: Aim for 80%+ coverage
- Critical paths (auth, RBAC): 90%+ coverage

**How to Run Locally**:
```bash
pytest server/tests
pytest server/tests -v  # Verbose
pytest server/tests -k test_auth  # Run specific test
```

### Backend Success Criteria

✅ All three checks pass (ruff + mypy + pytest)
✅ No critical security warnings
✅ Test coverage doesn't decrease significantly

## Frontend Quality Gates (Node.js)

### Job: `frontend`

**Environment**:
- Ubuntu latest
- Node.js 20 (primary), Node.js 18 (compatibility)

**Required Steps**:

#### 1. Linting (ESLint)
**Purpose**: Enforce code style and React best practices
**Command**: `npm run lint` (or `eslint src/`)
**Blocking**: ✅ Yes - must pass

**Common Issues**:
- React hooks dependency warnings
- Unused variables
- Console.log statements in production code
- Missing key props in lists

**How to Fix Locally**:
```bash
cd client
npm run lint
npm run lint -- --fix  # Auto-fix some issues
```

**Note**: If linting script doesn't exist yet, add to `package.json`:
```json
"scripts": {
  "lint": "eslint src/ --ext .ts,.tsx"
}
```

#### 2. Type Checking (TypeScript)
**Purpose**: Catch type errors in TypeScript code
**Command**: `tsc --noEmit`
**Blocking**: ✅ Yes - must pass

**Common Issues**:
- Type mismatches
- Missing type definitions
- Incorrect prop types
- Nullable type access

**How to Fix Locally**:
```bash
cd client
npx tsc --noEmit
```

**Windows (paths containing `&`)**:
```powershell
Set-Location client
node node_modules/typescript/bin/tsc --noEmit
```

#### 3. Unit Tests (Jest/React Testing Library)
**Purpose**: Test components and hooks
**Command**: `npm test -- --watchAll=false --coverage`
**Blocking**: ✅ Yes - must pass

**Coverage Requirements**:
- Minimum: 60% overall coverage (aspirational)
- New components: Aim for 70%+
- Critical flows (auth, session): 80%+

**How to Run Locally**:
```bash
cd client
npm test
npm test -- --watchAll=false  # Run once
npm test -- --coverage  # With coverage
```

**Windows (paths containing `&`)**:
```powershell
Set-Location client
$env:CI='true'
node node_modules/react-scripts/bin/react-scripts.js test --watchAll=false
```

#### 4. Build Check
**Purpose**: Ensure production build succeeds
**Command**: `npm run build`
**Blocking**: ✅ Yes - must pass

**Common Issues**:
- Build errors from type issues
- Missing environment variables (should have defaults)
- Asset size warnings (should optimize if >500KB)

**How to Fix Locally**:
```bash
cd client
npm run build
```

**Windows (paths containing `&`)**:
```powershell
Set-Location client
$env:CI='true'
node node_modules/react-scripts/bin/react-scripts.js build
```

### Frontend Success Criteria

✅ All four checks pass (eslint + tsc + tests + build)
✅ No TypeScript errors
✅ Build completes successfully
✅ No security vulnerabilities in dependencies (npm audit)

## Optional Quality Gates

### Smoke Testing (Playwright)

**Job**: `smoke` (optional, can be marked as non-blocking)

**Purpose**: Basic E2E validation of critical flows
**When to Run**: After backend and frontend jobs pass

**Test Scenarios**:
1. Backend starts successfully
2. API health check responds
3. Basic endpoint smoke test (auth, campaigns)

**Blocking**: ⚠️ Optional - recommend non-blocking initially

**Why Optional?**:
- E2E tests can be flaky
- Require more infrastructure
- Should stabilize before making blocking

**How to Enable as Blocking**:
When smoke tests are stable (>95% pass rate over 2 weeks), make blocking by removing `continue-on-error: true`.

## CI Failure Handling

### When CI Fails

1. **Review Logs**: Click on failed job in GitHub Actions
2. **Reproduce Locally**: Run the exact same command locally
3. **Fix Issues**: Address errors following guidance above
4. **Push Fix**: Commit and push - CI runs automatically
5. **Verify**: Ensure all checks pass

### Common CI Issues

#### Issue: Tests pass locally but fail in CI
**Causes**:
- Environment differences (Node/Python versions)
- Missing dependencies
- Timing issues (tests too fast/slow)
- Hardcoded paths or assumptions

**Solutions**:
- Match CI environment locally
- Add all dependencies to requirements.txt/package.json
- Add proper waits/retries
- Use relative paths

#### Issue: Flaky tests (sometimes pass, sometimes fail)
**Causes**:
- Race conditions
- Network dependencies
- Random data without seeds
- Shared state between tests

**Solutions**:
- Add proper async handling
- Mock external services
- Use fixed seeds for random data
- Isolate test state (fixtures, cleanup)

**Policy**: 
- Flaky tests must be fixed or skipped
- Don't merge if tests are unreliable
- Track flaky tests in issues

#### Issue: Build takes too long (>10 minutes)
**Causes**:
- Dependency installation not cached
- Running full test suite multiple times
- Large artifacts being uploaded

**Solutions**:
- Enable caching (package-lock.json, pip cache)
- Run tests in parallel
- Optimize test selection

## Blocking vs Non-Blocking Guidance

### Always Blocking ✅

These **must** pass before merging:

- ✅ Backend linting (ruff)
- ✅ Backend unit tests (pytest)
- ✅ Frontend linting (eslint)
- ✅ Frontend type checking (tsc)
- ✅ Frontend unit tests (jest)
- ✅ Frontend build
- ✅ No critical security vulnerabilities

**Rationale**: These catch bugs early and maintain code quality.

### Conditionally Blocking ⚠️

These should block once stable:

- ⚠️ Backend type checking (mypy) - non-blocking until codebase is typed
- ⚠️ Smoke tests (E2E) - block when >95% reliable
- ⚠️ Integration tests - block when comprehensive
- ⚠️ Performance tests - block when baselines established

**Rationale**: Important but can be flaky or incomplete initially.

### Never Blocking ❌

These are informational only:

- ❌ Code coverage reports (enforce minimums but don't block on exact %)
- ❌ Bundle size analysis (warn but don't block)
- ❌ Deprecation warnings (fix but don't block)
- ❌ Style suggestions (autoformat instead)

**Rationale**: Helpful but shouldn't prevent merging working code.

## Bypass Procedures

### When to Bypass CI

Only in emergencies:

- Critical security hotfix
- Production outage fix
- CI infrastructure is broken

### How to Bypass

1. **Request Approval**: Get maintainer approval
2. **Document Reason**: Add comment to PR explaining why
3. **Create Issue**: Track technical debt to fix properly
4. **Merge**: Use admin override (requires permissions)
5. **Follow Up**: Fix issues in next PR

**Example**:
```
Bypassing CI for emergency fix of [CVE-2024-XXXX]
Created issue #123 to add proper tests
```

## CI Optimization Tips

### Speed Up CI

1. **Cache Dependencies**: Use GitHub Actions cache
2. **Parallel Jobs**: Run backend/frontend concurrently (already done)
3. **Fail Fast**: Exit on first error
4. **Selective Tests**: Run affected tests first
5. **Efficient Docker**: Use slim images, multi-stage builds

### Improve Reliability

1. **Lock Versions**: Pin exact dependency versions
2. **Retry Flaky Steps**: Add retry logic for network operations
3. **Timeout Guards**: Set reasonable timeouts
4. **Clear Logs**: Make errors easy to diagnose
5. **Regular Maintenance**: Update dependencies monthly

## Quality Metrics Dashboard

### Track These Metrics

- **Pass Rate**: % of PRs passing CI on first try (target: 80%+)
- **Avg Time**: Time from PR to merge (target: <1 day)
- **Flaky Tests**: Number of flaky tests (target: 0)
- **Coverage**: Code coverage trend (target: increasing)
- **Build Time**: Total CI duration (target: <10 min)

### Monthly Review

Review metrics monthly and:
- Identify bottlenecks
- Fix flaky tests
- Optimize slow steps
- Update this document

## Getting Help

### CI is Red ❌

1. Read error message carefully
2. Run command locally
3. Check this document for guidance
4. Search GitHub issues for similar problems
5. Ask in Discord/Slack (if applicable)
6. Create issue if truly stuck

### CI is Unclear

1. Check job logs in GitHub Actions
2. Review this checklist
3. Ask maintainer for clarification
4. Suggest improvements to this doc

## Checklist for PR Authors

Before requesting review:

- [ ] All CI jobs pass (green ✓)
- [ ] Linting passes locally
- [ ] Type checking passes locally
- [ ] All tests pass locally
- [ ] Build succeeds locally
- [ ] Added tests for new functionality
- [ ] Updated documentation if needed
- [ ] No security warnings
- [ ] Commit messages are clear

## Checklist for Reviewers

Before approving PR:

- [ ] All CI jobs pass
- [ ] Code changes align with PR description
- [ ] Tests cover new functionality
- [ ] No obvious security issues
- [ ] Documentation updated if needed
- [ ] Breaking changes are documented
- [ ] Migrations (if any) are safe

---

_Last Updated: 2026-01-09 | Maintainer: TavernTAIls Core Team_
