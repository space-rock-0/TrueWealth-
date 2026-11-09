# Bank statement integration

Open **Bank Statements** next to **AI Advisor** after signing in. The statement workspace shares the existing authentication, CSRF protection, PostgreSQL/SQLite database, and AI provider settings. Supported providers remain Groq, OpenAI, Anthropic, and Gemini.

## Features

- Upload searchable or scanned PDFs, UTF-8 CSV, and text files.
- Upload batches of up to 10 files, processing each file independently so one failure does not discard successful files. Once an analysis is submitted, it runs as a server background task even if the tab closes. Keep the page open to submit the remaining files in a batch. Saved documents remain available for retry after interruption.
- Extract scanned pages with CPU OCR on the server. Page images are not sent to cloud providers. Limits: 10 MB per file, 100 PDF pages, at most 20 OCR pages per PDF, 180,000 extracted characters, and 200 saved statements per account.
- Redact common email addresses, account/phone numbers, and labelled identity/address lines before database storage and AI calls. This is pattern-based redaction, not a guarantee that every person's name or address is removed. Review documents before uploading.
- Extract dated, categorized transactions with validated nonnegative credit/debit values and explicit currency. AI calls use the current user's selected provider and key; keys are not stored in statement records.
- Detect identical file uploads within an account.
- Preserve document history, transaction tables, failed extraction status, retry, and permanent deletion.
- Aggregate annual/quarterly cash flows, monthly totals, and debit categories. Compute monetary totals using decimal arithmetic on the server; keep currencies separate. Different overlapping statements may contain duplicate transactions.
- Download CSV and Markdown reports, or use browser print to save PDF. CSV descriptions are protected against spreadsheet formula injection.
- Ask questions using retrieved document excerpts plus computed whole-statement summaries. Answers include excerpt references where appropriate. The source data is treated as untrusted input.
- Access statements through the MCP stdio bridge described below.

The bank-statement product workflows were implemented natively in TrueWealth. The source repository's unfinished Deep Agents/Hermes adapters are not presented as working features. Local model engines and GPU dashboards are excluded by the user's choice to retain four cloud providers. The original repository is retained in the root with its original license; this integration does not need to start its separate API, frontend, Qdrant, or authentication service. Analyses use server background tasks with persisted status, not a Celery queue. Provider keys are transient and are not saved to a task queue or database. On server restart, interrupted jobs are marked failed and can be retried with the user's provider settings. Run one API worker with this recovery model; a multiworker deployment needs a separate coordinated job queue before enabling additional workers.

## Setup

Install the updated `backend/requirements.txt` with Python 3.12. The OCR dependencies include bundled model weights. The backend Dockerfile includes OpenCV's Linux runtime libraries. A native Linux deployment must provide `libGL.so.1` and GLib, or use the Docker build.

The existing production database and SMTP settings still apply. The new `statement` table is created at backend startup. No external vector database or new secret is required. The frontend Nginx proxy now accepts 15 MB HTTP bodies and allows up to 180 seconds for analysis requests.

## Manual check

1. Sign in, open AI Provider Settings, select one of the four providers, and supply a valid API key/model.
2. Open Bank Statements and upload one searchable PDF or CSV. Confirm transaction dates, amounts, currencies, and categories against the source.
3. Upload a scanned PDF; confirm OCR extracts readable transactions. Unreadable/encrypted/oversized files should show actionable errors.
4. Select several files at once. Successful files should remain in history even if another file fails.
5. Re-upload an identical file: it should reuse the existing document, avoiding duplicate history.
6. Change the dashboard year/quarter. Confirm totals and categories, and download a report. Different currencies must remain separate.
7. Open a document, ask a question, export CSV/Markdown, and print to PDF.
8. Sign out and use a second account. It must not see or fetch the first account's documents, analytics, exports, or answers.
9. Delete a statement and refresh. It must disappear from history and totals.

## MCP

Start the bridge with `backend/.venv/Scripts/python.exe -m app.mcp_server`, setting the working directory to `backend`. Configure the environment through your MCP client:

- `TRUEWEALTH_API_URL`: `http://127.0.0.1:5001` locally, or the HTTPS API origin remotely.
- `TRUEWEALTH_MCP_USERNAME`, `TRUEWEALTH_MCP_PASSWORD`: a verified account's email/username and password. The bridge signs in normally and retains cookies only in memory.
- `TRUEWEALTH_MCP_PROVIDER`: one of the four cloud providers.
- `TRUEWEALTH_MCP_MODEL`: optional model override.
- `TRUEWEALTH_MCP_API_KEY`: optional user provider key; otherwise the server fallback key applies.

Tools: `list_statements`, `get_statement`, `analyze_statement`, `ask_statement`, and `financial_summary`. AI analysis/question tools may incur charges. Restart the bridge after its account session expires. Do not commit MCP credentials to repository files.

## Verification

`backend/tests/test_statements_integration.py` checks ownership boundaries, duplicate detection, validation, background processing, quarterly totals, CSV formula handling, redaction, and MCP negotiation using a mocked AI response. `backend/scripts/check_statement_ocr.py` creates a synthetic scanned PDF and runs the actual CPU OCR pipeline without a paid API request. `backend/scripts/check_statement_flow.py` checks the running local API with temporary accounts and cleans them up afterward. Live extraction quality still needs manual review with real bank statement formats and the chosen provider.
