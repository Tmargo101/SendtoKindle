# Send to Kindle

Private service that accepts article URLs, converts them into EPUB files, and emails them to a Kindle address.

## Features
- FastAPI endpoint for queueing article URLs.
- SQLite-backed job queue shared by API and worker services.
- Article extraction with `trafilatura`.
- Text-first EPUB generation with optional lead image support.
- SMTP delivery to Kindle email addresses.
- Dockerized API and worker deployment via Docker Compose.

## Quick start
1. Use Python 3.12+ for local runs, or use Docker.
2. Copy `.env.example` to `.env` and fill in SMTP settings.
3. Copy `config/users.example.yaml` to `config/users.yaml`.
4. Replace `token_hash` with `sha256(<your-api-token>)`, for example:
   ```bash
   python3 - <<'PY'
   import hashlib
   print(hashlib.sha256(b"replace-me").hexdigest())
   PY
   ```
5. Start the stack:
   ```bash
   docker compose up --build
   ```
6. Queue an article:
   ```bash
   curl -X POST http://localhost:6122/v1/articles \
     -H 'Authorization: Bearer <your-api-token>' \
     -H 'Content-Type: application/json' \
     -d '{"url":"https://example.com/article"}'
   ```

## Unraid setup
There are now two ways to deploy this:
- `docker-compose.yml`: builds the image from source on the host
- `docker-compose.image.yml`: pulls a prebuilt image, which is the simpler Unraid path

These steps are for the simpler Unraid path using a prebuilt image.

1. On Unraid, create a folder for the app data.
   A simple layout is:
   ```text
   /mnt/user/appdata/send-to-kindle/
   ```
   Inside it, create these folders and files:
   ```text
   docker-compose.image.yml
   .env
   data/
   artifacts/
   config/users.yaml
   ```
   You do not need to copy the Python source code when using the prebuilt image.

2. Copy these files to Unraid:
   - `.env.example`
   - `docker-compose.image.yml`
   - `config/users.example.yaml`

3. Create your environment file.
   Copy `.env.example` to `.env`, then edit the values.
   The important SMTP settings are:
   - `STK_SMTP_HOST`
   - `STK_SMTP_PORT`
   - `STK_SMTP_USERNAME`
   - `STK_SMTP_PASSWORD`
   - `STK_SMTP_SENDER`
   Add one more line for the image name:
   ```text
   STK_IMAGE=ghcr.io/YOUR-GITHUB-USER/send-to-kindle:latest
   ```

4. Create your user config.
   Copy `config/users.example.yaml` to `config/users.yaml`.

5. Create an API token hash.
   Pick any secret token you want to use from your phone or scripts.
   Run this command and save the output:
   ```bash
   python3 - <<'PY'
   import hashlib
   print(hashlib.sha256(b"replace-with-your-token").hexdigest())
   PY
   ```
   Put that value into `config/users.yaml` as `token_hash`.

6. Add your Kindle email.
   In `config/users.yaml`, set:
   - `kindle_email` to your Kindle Send-to-Kindle address
   - `user_id` to any short name you want

7. Start the containers.
   From the project folder, run:
   ```bash
   docker compose -f docker-compose.image.yml up -d
   ```

8. Confirm the API is running.
   Open:
   ```text
   http://YOUR-UNRAID-IP:6122/healthz
   ```
   You should see:
   ```json
   {"status":"ok"}
   ```

9. Send a test article.
   Replace `YOUR_TOKEN` with the plain token you chose earlier:
   ```bash
   curl -X POST http://YOUR-UNRAID-IP:6122/v1/articles \
     -H 'Authorization: Bearer YOUR_TOKEN' \
     -H 'Content-Type: application/json' \
     -d '{"url":"https://example.com/article"}'
   ```

10. Check job status.
   The first request returns a `jobId`.
   Use it here:
   ```bash
   curl http://YOUR-UNRAID-IP:6122/v1/jobs/JOB_ID \
     -H 'Authorization: Bearer YOUR_TOKEN'
   ```

### Unraid notes
- Put everything under `appdata` so your database and generated files survive container restarts.
- The service writes SQLite data to `data/` and temporary EPUB files to `artifacts/`.
- If port `6122` is already in use on Unraid, change the left side of `6122:6122` in `docker-compose.image.yml`.
- If your Kindle does not receive the file, check:
  - SMTP credentials
  - That your sender address is allowed by your mail provider
  - That the sender address is approved in Amazon's Send-to-Kindle settings
- After you change `config/users.yaml` or `.env`, restart the stack:
  ```bash
  docker compose -f docker-compose.image.yml up -d
  ```

## Publishing a prebuilt image
If you want Unraid to pull an image instead of building from source, publish this repo's Docker image first.

This repo now includes a GitHub Actions workflow that pushes to:
```text
ghcr.io/<your-github-user>/send-to-kindle:latest
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
send-to-kindle worker
```

## Notes
- Only public `http` and `https` article URLs are supported.
- Authentication is static bearer-token based.
- User definitions are loaded from `config/users.yaml` on process start.
- Generated EPUB files are kept temporarily for retry/debug and cleaned up by the worker.
