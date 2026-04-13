# Unraid Deployment

This guide is the recommended way to run Send to Kindle on Unraid.

It assumes:
- you want to use the published image at `ghcr.io/tmargo101/send-to-kindle:latest`
- you are using Unraid's Compose Manager or a compatible Docker Compose workflow
- you want persistent data under `/mnt/user/appdata/`

## Why this path
This project now runs as a single container:
- `app` serves the API and runs the background article processor in the same process

The supported Unraid path is still `docker-compose.image.yml` because it keeps the image, env file, mounts, and restart policy together in one place.

## Files you need
Copy these files from the repo:
- `docker-compose.image.yml`
- `.env.example`
- `config/users.example.yaml`

You do not need to copy the Python source code when using the published image.

## Recommended Unraid folder layout
Create this appdata folder on your Unraid host:

```text
/mnt/user/appdata/send-to-kindle/
```

Use this layout inside it:

```text
/mnt/user/appdata/send-to-kindle/
  docker-compose.image.yml
  .env
  data/
  artifacts/
  config/
    users.yaml
```

What each path is for:
- `.env`: SMTP settings and optional image override
- `config/users.yaml`: Kindle destination and API token hashes
- `data/`: persistent SQLite database
- `artifacts/`: temporary EPUB files and retry artifacts

## Step 1: Copy the compose file
Place `docker-compose.image.yml` in:

```text
/mnt/user/appdata/send-to-kindle/docker-compose.image.yml
```

The compose file already points at the published GHCR image:

```text
ghcr.io/tmargo101/send-to-kindle:latest
```

If you want to pin a different tag later, set `STK_IMAGE` in `.env`.

## Step 2: Create `.env`
Copy `.env.example` to:

```text
/mnt/user/appdata/send-to-kindle/.env
```

Set these required values:
- `STK_SMTP_HOST`
- `STK_SMTP_PORT`
- `STK_SMTP_USERNAME`
- `STK_SMTP_PASSWORD`
- `STK_SMTP_SENDER`

Optional browser fetch settings:
- `STK_BROWSER_FETCH_ENABLED=true`
- `STK_BROWSER_FETCH_TIMEOUT_SECONDS=30`

Leave this at its default unless you change the file mount:

```text
STK_USERS_CONFIG_PATH=/app/config/users.yaml
```

Optional image override:

```text
STK_IMAGE=ghcr.io/tmargo101/send-to-kindle:latest
```

## Step 3: Create `config/users.yaml`
Copy `config/users.example.yaml` to:

```text
/mnt/user/appdata/send-to-kindle/config/users.yaml
```

Then update:
- `user_id` with any short name you want
- `display_name` with a friendly label
- `kindle_email` with your Send-to-Kindle address
- `token_hash` with a SHA-256 hash of the API token you want to use

To generate `token_hash`, run:

```bash
python3 - <<'PY'
import hashlib
print(hashlib.sha256(b"replace-with-your-token").hexdigest())
PY
```

Keep the plain token you chose. You will use that plain token in API requests later.

## Step 4: Start the stack on Unraid
From `/mnt/user/appdata/send-to-kindle/`, start the services with:

```bash
docker compose -f docker-compose.image.yml up -d
```

This starts:
- `app` on port `6122`
- the built-in background worker for article processing

If port `6122` is already in use on your Unraid box, change the host side of `6122:6122` in `docker-compose.image.yml`.

## Step 5: Validate the deployment
Check the health endpoint:

```text
http://YOUR-UNRAID-IP:6122/healthz
```

Expected response:

```json
{"status":"ok"}
```

## Step 6: Send a first test article
Use the plain token you picked before, not the hash stored in `users.yaml`.

```bash
curl -X POST http://YOUR-UNRAID-IP:6122/v1/articles \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com/article"}'
```

The response includes a `jobId`.

Check that job:

```bash
curl http://YOUR-UNRAID-IP:6122/v1/jobs/JOB_ID \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

## Updating or restarting
After changing `.env` or `config/users.yaml`, apply the changes with:

```bash
docker compose -f docker-compose.image.yml up -d
```

## Troubleshooting
If the API does not come up:
- confirm that `docker-compose.image.yml` is using the published image or the correct `STK_IMAGE` override
- confirm port `6122` is not already bound by another container
- confirm `config/users.yaml` exists at `/mnt/user/appdata/send-to-kindle/config/users.yaml`

If jobs are accepted but Kindle email never arrives:
- confirm your SMTP host, port, username, password, and sender are correct
- confirm the sender address is allowed by your mail provider
- confirm the sender address is approved in Amazon Send-to-Kindle settings

If blocked or JS-heavy articles fail:
- confirm you are using a current image build that includes the bundled Chromium runtime
- confirm `STK_BROWSER_FETCH_ENABLED=true` in `.env`
- inspect the container logs for whether the request succeeded via normal HTTP fetch or browser fallback

If you want to inspect container state, run:

```bash
docker compose -f docker-compose.image.yml ps
```

## Summary
For Unraid, the intended deployment path is:
1. Keep everything under `/mnt/user/appdata/send-to-kindle/`
2. Use `docker-compose.image.yml`
3. Pull `ghcr.io/tmargo101/send-to-kindle:latest`
4. Persist `data/`, `artifacts/`, and `config/users.yaml`
5. Validate with `/healthz` and one real test article
