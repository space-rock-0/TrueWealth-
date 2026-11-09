# Deployment

The free deployment uses Vercel for the static frontend, one Render Docker web service in Singapore for the API, and a dedicated Neon PostgreSQL project in Singapore. Both hosting services track `main` in `space-rock-0/TrueWealth-`.

## Configuration

Frontend: `frontend/vercel.json` proxies `/api/*` to the backend so browser cookies remain on the frontend origin. Its Vercel project root is `frontend`. Only public settings such as `VITE_MAX_OCR_PAGES=4` belong in Vercel build variables.

Backend: `render.yaml` documents the service settings. Actual provisioning is performed through the Render plugin; later Blueprint adoption should reuse the same resource and preserve secrets. Set `APP_ENV=production`, `EMAIL_VERIFICATION_REQUIRED=true`, `RATE_LIMIT_ENABLED=true`, `DATABASE_URL`, `FRONTEND_URL`, and `APP_ALLOWED_ORIGINS`. Keep one API worker. Database connections and email keys belong only in Render environment variables, never GitHub or Vercel frontend variables.

Email on Render's free plan uses HTTPS. Configure `EMAIL_PROVIDER=brevo`, `EMAIL_FROM` to a verified sender, and `BREVO_API_KEY` to an active Brevo API key. A Brevo SMTP key cannot authenticate the HTTPS API. Alternatively configure Resend with `EMAIL_PROVIDER=resend`, `EMAIL_FROM`, and `RESEND_API_KEY` for a verified sending domain. Public registration stays closed while email credentials are missing. Never disable email verification to bypass email setup.

Users can provide their own Groq, OpenAI, Anthropic, or Gemini keys in Settings. A shared provider key is optional and should be set only as a backend secret if required.

## Free-tier resource limits

Render's free web service has 512 MB RAM, sleeps when idle, has an ephemeral filesystem, and blocks SMTP ports. It does not provide always-on production uptime. See [Render's current limitations](https://render.com/docs/free).

The cloud image installs `requirements-production.txt`, excluding PyTorch and the local embedding model. It uses bounded lexical retrieval and PostgreSQL chat history instead. OCR runs in a short-lived subprocess to release its model memory; it is limited to four scanned pages per file with a maximum rendered image edge of 1,800 pixels. Searchable PDFs can contain up to 100 pages. Larger scanned statements should be split or exported as bank CSV.

An analysis already submitted to the server continues after the browser tab closes. Its provider key remains in memory only. Stale analysis jobs are marked retryable after ten minutes, avoiding premature cancellation during a rolling deploy. A restart can interrupt a job; there is no persistent external job queue. Do not scale to multiple API workers until job coordination and distributed rate limiting are implemented.

The production database starts empty; local `.env`, accounts, statements, SQLite databases, vector memory, and logs are excluded from Git. Any requested data migration should be a separate authenticated operation with a backup.

## Release checks

Run backend tests, frontend lint/tests/build, isolated OCR smoke tests, and `backend/scripts/check_publication.py` before pushing. After deployment, verify frontend HTML, proxied API health, CSRF bootstrap, secure session cookies, registration email, sign-in, statement ownership, uploads, extraction with a user key, exports, and sign-out. Confirm that a new deployment still reads the same PostgreSQL records. A platform build success alone is not full application verification.
