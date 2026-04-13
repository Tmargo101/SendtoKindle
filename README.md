# Send to Kindle

Private service that accepts article URLs, converts them into EPUB files, and emails them to a Kindle address.

## Features
- FastAPI endpoint for queueing article URLs.
- SQLite-backed job queue processed by an in-process background worker.
- Article extraction with `trafilatura`.
- Text-first EPUB generation with optional lead image support.
- SMTP delivery to Kindle email addresses.
- Single-container Docker deployment via Docker Compose.

## Quick start
1. Use Python 3.12+ for local runs, or use Docker.
2. Copy `.env.example` to `.env`.
3. Set these values in `.env`:
   - `STK_SMTP_HOST`
   - `STK_SMTP_PORT`
   - `STK_SMTP_USERNAME`
   - `STK_SMTP_PASSWORD`
   - `STK_SMTP_SENDER`
   - `STK_USERS_CONFIG_PATH` if you want your user file somewhere other than `./config/users.yaml`
4. Copy `config/users.example.yaml` to `config/users.yaml`.
5. Replace `token_hash` with `sha256(<your-api-token>)`, for example:
   ```bash
   python3 - <<'PY'
   import hashlib
   print(hashlib.sha256(b"replace-me").hexdigest())
   PY
   ```
6. Start the stack:
   ```bash
   docker compose up --build
   ```
7. Queue an article:
   ```bash
   curl -X POST http://localhost:6122/v1/articles \
     -H 'Authorization: Bearer <your-api-token>' \
     -H 'Content-Type: application/json' \
     -d '{"url":"https://example.com/article"}'
   ```

For normal deployments, the service now uses built-in defaults for the database, artifact, retry, and logging paths/settings. Advanced `STK_*` overrides still work, but they are intentionally omitted from the default setup flow.

## GHCR image workflow
If you do not want to copy the Python source code to your server, use the published Docker image instead.

Published image:
```text
ghcr.io/tmargo101/send-to-kindle:latest
```

Use this file for image-based deployment:
```text
docker-compose.image.yml
```

Basic steps:
1. Copy these files to your server:
   - `docker-compose.image.yml`
   - `.env`
   - `config/users.yaml`
2. Create these folders next to them:
   - `data/`
   - `artifacts/`
3. Fill in the SMTP values in `.env`.
4. Optionally set this in `.env` if you want a non-default image tag:
   ```text
   STK_IMAGE=ghcr.io/tmargo101/send-to-kindle:latest
   ```
5. Start the stack:
   ```bash
   docker compose -f docker-compose.image.yml up -d
   ```

This workflow is useful for Unraid or any host where you want to pull a ready-made image instead of building from source.

## Unraid deployment
Use [docs/unraid.md](docs/unraid.md) for the recommended Unraid-first setup.

That guide is intentionally separate from the source-build workflow above and focuses on:
- Unraid Compose Manager with `docker-compose.image.yml`
- exact `/mnt/user/appdata/send-to-kindle/` folder layout
- GHCR image configuration
- first-run health checks and test article validation

Why Compose Manager instead of a single Unraid Docker template:
- it still gives you a clean, reproducible deployment for the app image, env file, and volume mounts
- it maps well to Unraid appdata folder layouts
- that keeps the supported Unraid path explicit with the least guesswork

## Publishing a prebuilt image
If you want Unraid to pull an image instead of building from source, publish this repo's Docker image first.

This repo now includes a GitHub Actions workflow that pushes to:
```text
ghcr.io/tmargo101/send-to-kindle:latest
```

The workflow file is:
```text
.github/workflows/publish-image.yml
```

Run it by either:
- publishing a GitHub release
- manually triggering the workflow in GitHub Actions

Once that image exists, Unraid only needs:
- `docker-compose.image.yml`
- `.env`
- `config/users.yaml`
- `data/`
- `artifacts/`

## Running without Docker
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install .
send-to-kindle api
```

When running outside Docker, the app stores its data under the current working directory by default:
- `./data/send_to_kindle.db`
- `./artifacts/`
- `./config/users.yaml`

## Notes
- Only public `http` and `https` article URLs are supported.
- Authentication is static bearer-token based.
- User definitions are loaded from `config/users.yaml` on process start.
- Generated EPUB files are kept temporarily for retry/debug and cleaned up by the background worker.
