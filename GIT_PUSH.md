# Creating a GitHub repository and pushing the current project

This file contains step-by-step commands you can run locally to create a GitHub repo, add it as a remote, and push the current branch. I cannot run these commands from here, but you can copy/paste them into PowerShell.

Replace `<OWNER>` and `<REPO>` with your GitHub account/org and desired repository name.

1) Create the remote repository on GitHub (recommended via web UI)
   - Go to https://github.com/new and create a repository named `<REPO>` (public/private as desired).

2) Locally: initialize git (if not already) and prepare commit

```powershell
cd C:\Users\colem\OneDrive\solottrpg
# If needed: initialize and set a main branch name
git init
git checkout -b main

# Stage all files and create a focused commit
git add -A
# Recommended commit message summarizing recent large changes
git commit -m "chore: rename project to TavernTAIls; add DB-backed Campaigns & Rolls, session membership, dev tooling, and initial frontend wiring"
```

3) Add GitHub remote and push

```powershell
# Create remote (replace <OWNER> and <REPO>)
git remote add origin git@github.com:<OWNER>/<REPO>.git
# Or use HTTPS:
# git remote add origin https://github.com/<OWNER>/<REPO>.git

# Push main branch and set upstream
git push -u origin main
```

4) After pushing
- Enable GitHub Actions if you want CI; `.github/workflows/ci.yml` is present.
- Add repository secrets (Settings → Secrets) for production env vars if needed (e.g. `TAVERNTAILS_SECRET`).

Hints and optional extras
- If your repo already has commits and you need to preserve history, skip `git init` and just add remote + push.
- If you prefer a feature branch workflow, push to a branch like `feature/campaign-sessions` and open a PR on GitHub.
- For GitHub CLI users, you can create the remote from the command line:
  `gh repo create <OWNER>/<REPO> --public --source=. --remote=origin --push`

If you want, I can also create a minimal `PR_TEMPLATE.md` and `ISSUE_TEMPLATE.md` next.
