# TavernTAIls — Staging & Preview Deployments

This document explains how to stand up a live test version of TavernTAIls and
how GitHub automatically rebuilds and (optionally) redeploys it whenever code
is merged.

---

## How it works

The [`.github/workflows/deploy-staging.yml`](../.github/workflows/deploy-staging.yml)
workflow fires on every push to `main` or `develop` and does two things:

1. **Build** the full-stack Docker image (React frontend + FastAPI backend in
   one container) and **push** it to GitHub Container Registry (GHCR) at
   `ghcr.io/<org>/taverntails`.
2. *(Optional)* **SSH into a staging server** and swap in the new container.

You can pull the published image from GHCR and run it on any machine — a
laptop, a cloud VM, Railway, Render, Fly.io, etc.

---

## Quick start (Docker Compose)

```bash
# 1. Clone the repo (or just copy docker-compose.yml)
git clone https://github.com/DegeneratesAnonymous/TavernTails.git
cd TavernTails

# 2. Set your JWT secret (mandatory) and, optionally, your OpenAI key
export TAVERNTAILS_SECRET="change-me-to-something-random"
export OPENAI_API_KEY="sk-..."          # optional — only needed for AI features

# 3. Build and start
docker compose up --build

# The app is now reachable at http://localhost:8000
# Default login: test@example.com / secret
```

To pick up the latest pre-built image from GHCR instead of building locally:

```bash
# Pull the image that was built by CI for the main branch
docker pull ghcr.io/degeneratesanonymous/taverntails:latest

# Then run it
docker run -d \
  --name taverntails-staging \
  --restart unless-stopped \
  -p 8000:8000 \
  -v taverntails_data:/app/data \
  -e TAVERNTAILS_SECRET="change-me" \
  -e OPENAI_API_KEY="sk-..." \
  ghcr.io/degeneratesanonymous/taverntails:latest
```

Data (SQLite database) is persisted in the `taverntails_data` Docker volume,
so it survives container restarts and image updates.

---

## Enabling automatic SSH re-deploys (optional)

If you have a server you'd like GitHub to deploy to automatically on every
merge to `main`, configure the following in your repository settings:

### Repository variable (Settings → Variables → Actions)

| Variable name            | Value  |
|--------------------------|--------|
| `STAGING_DEPLOY_ENABLED` | `true` |

### Repository secrets (Settings → Secrets → Actions)

| Secret name        | Description                                          |
|--------------------|------------------------------------------------------|
| `DEPLOY_SSH_HOST`  | Hostname or IP of the staging server                 |
| `DEPLOY_SSH_USER`  | SSH username (e.g. `ubuntu`, `deploy`)               |
| `DEPLOY_SSH_KEY`   | Private SSH key (the public key must be on the host) |
| `DEPLOY_SSH_PORT`  | *(optional)* SSH port — defaults to `22`             |

The server needs Docker installed and the GitHub Container Registry image must
be accessible (it is public by default for public repos).

> **Security note:** Use a dedicated deploy key with minimal permissions.
> Never reuse personal SSH keys.  See `docs/SECRET_MANAGEMENT.md` for key
> rotation guidance.

### Server-side environment variables

On the staging server, export `TAVERNTAILS_SECRET` and (optionally)
`OPENAI_API_KEY` in the shell environment that runs the deploy command, or
store them in a `.env` file sourced by the deploy user's profile.

---

## Image tags

| Tag           | When it is updated              |
|---------------|---------------------------------|
| `latest`      | Every push to `main`            |
| `develop`     | Every push to `develop`         |
| `sha-<hash>`  | Every push to `main`/`develop`  |

---

## Environment variables reference

| Variable                   | Default                                  | Description                                   |
|----------------------------|------------------------------------------|-----------------------------------------------|
| `TAVERNTAILS_DATABASE_URL` | `sqlite:////app/data/taverntails.db`     | SQLAlchemy connection string                  |
| `TAVERNTAILS_SECRET`       | `dev-secret-change-me`                   | JWT signing secret — **change in production** |
| `OPENAI_API_KEY`           | *(empty)*                                | Enables AI agent features                     |
| `TAVERNTAILS_SEED_DEV_USER`| `1`                                      | Set to `0` to skip seeding `test@example.com` |

---

## Updating the staging deployment manually

```bash
docker pull ghcr.io/degeneratesanonymous/taverntails:latest
docker stop taverntails-staging
docker rm   taverntails-staging
docker run -d \
  --name taverntails-staging \
  --restart unless-stopped \
  -p 8000:8000 \
  -v taverntails_data:/app/data \
  -e TAVERNTAILS_SECRET="$TAVERNTAILS_SECRET" \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  ghcr.io/degeneratesanonymous/taverntails:latest
```
