# Knowledge Assistant (RAG)

A retrieval-augmented chat assistant with two separate interfaces:

- **Chat** at `/`: ask questions about the knowledge base, get streamed answers with clickable source
  citations, and keep a conversation history.
- **Admin dashboard** at `/admin` (the **Admin** button in the chat): upload and manage documents, watch
  ingestion status and logs, and rebuild the index.

There are **no accounts or passwords**. Everyone who can open the app shares one workspace, including the
conversation list, and can use the admin dashboard. By default the server only listens on `127.0.0.1`
(this computer). Don't expose it on a network unless everyone there should be able to upload and delete
documents.

It runs on the Python standard library HTTP server with vanilla JavaScript, so there is no build step and no
web framework to install.

## Architecture

```text
app.py                   # entry point: builds the Application and serves HTTP
manage.py                # CLI: migrate, back up
api/
  application.py         # wiring + one dispatch path (CSRF, origin check, security headers, logging)
  http.py                # request/response/router primitives and server-sent events
  chat_routes.py         # /api/session, /api/conversations/*  chat (streamed answers)
  admin_routes.py        # /api/admin/*  documents, knowledge base, activity, health
  page_routes.py         # HTML pages and /static assets
core/
  config.py              # settings from environment variables
  database.py            # SQLite connection handling and schema migrations
  logging_setup.py       # structured logging (JSON in production)
services/
  workspace.py           # the single shared workspace that owns conversations
  conversation_service.py# conversation history
  document_service.py    # upload storage, background indexing, status, deletion, reindexing
  upload_validation.py   # file name, size, type, and content-signature checks
rag/
  embedder.py            # local hashing or OpenAI-compatible embeddings
  llm.py                 # OpenAI-compatible, Anthropic, and Gemini clients (with streaming)
  query.py               # retrieval, grounding prompt, citations, answer streaming
parsers/                 # PDF, Word, Excel, image OCR, JSON, text loaders
vectorstore/             # JSON vector store (thread-safe, atomic saves) + CLI tools
ui/admin.py              # chunking helpers
web/                     # chat.html, admin.html, static/css, static/js
storage/                 # app.db, vectors.json, documents/ (created at runtime)
tests/                   # unit and end-to-end tests
```

**How a question is answered:** the message is saved, the vector store returns the most relevant
chunks (weak matches are dropped), the chunks are numbered and sent to the LLM with instructions to cite them
and to say so when the answer isn't there, and the answer is streamed back to the browser over server-sent
events along with each source's document, page/section, and passage.

**How a document is ingested:** the admin uploads files. Each file is validated, checked for duplicates (SHA-256),
and stored as `storage/documents/<id>.<ext>`. It's queued as `queued`, and a background worker marks it `processing`,
parses → chunks → embeds it, then swaps its chunks into the index in a single atomic step and marks it `indexed`
(or `failed` with the error). Partially indexed documents are never searchable. Deleting a document removes
its vectors first, then its record and file.

## 1. Setup

```powershell
cd C:\Users\prane\Desktop\RAG
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env      # then edit .env
```

No new packages are required compared with the original project.

## 2. Run

```powershell
python app.py
```

Open `http://127.0.0.1:8000` for the chat. Click **Admin** (top right) or go to `/admin` to manage documents.

On first start, documents already in `storage/vectors.json` are imported into the dashboard automatically
(their original files weren't kept, so they're reindexed from their stored text if needed).

## Configuration

All settings live in `.env`; see `.env.example` for the full, commented list. The most important ones:

| Variable | Purpose |
|---|---|
| `APP_ENV` | `development` or `production` (JSON logs, no auto-opened browser) |
| `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL` | Answer generation. `none` gives retrieval-only answers |
| `LLM_TIMEOUT_SECONDS`, `LLM_THINKING_LEVEL` | Keep Gemini responsive (e.g. `30` and `low`) |
| `EMBEDDING_MODEL`, `EMBEDDING_BASE_URL`, `EMBEDDING_API_KEY` | Semantic embeddings. Empty = local hashing (keyword-like) |
| `MAX_UPLOAD_MB`, `MAX_FILES_PER_UPLOAD` | Upload limits |
| `CHAT_MESSAGES_PER_MINUTE`, `MAX_CONCURRENT_GENERATIONS` | Abuse and load limits |
| `APP_HOST` | `127.0.0.1` keeps the app private to this computer |
| `TRUST_PROXY` | Read client IP/host from a reverse proxy you control |

Any OpenAI-compatible API works for generation, including OpenAI, Groq, OpenRouter, Together, Ollama, and LM Studio:

```dotenv
LLM_PROVIDER=openai-compatible
LLM_MODEL=your-model
LLM_BASE_URL=http://localhost:11434/v1   # Ollama example
```

If you change the embedding model, the dashboard shows **Reindex required**. Run **Knowledge base → Reindex all
documents**. The old index keeps serving answers until the new one is complete. Changing `CHUNK_SIZE`/`CHUNK_OVERLAP`
isn't detected automatically; reindex all documents after changing them.

## Security model

- **No authentication.** Anyone who can reach the server can chat and use the admin dashboard. Keep
  `APP_HOST=127.0.0.1`, or put an authenticating reverse proxy (VPN, SSO, basic auth) in front of it if others
  need access.
- **Cross-site protection.** State-changing requests need the `X-CSRF-Token` from `/api/session` and a
  same-origin `Origin`. Other websites you visit can't upload, delete, or chat through your browser.
- **Uploads:** extension allow-list, per-file and per-request size limits, content-signature checks (e.g. a
  `.pdf` must start with `%PDF-`), sanitized names, and storage under server-generated names, so there's no
  path traversal. Static files are served only from `web/static`.
- **Headers:** strict Content-Security-Policy (no inline scripts), `X-Frame-Options: DENY`, `nosniff`.
- **Prompt injection:** the model is told to treat retrieved passages as reference only. Raw provider errors are
  never shown in the chat; details go to the server log.
- **Rate limits:** chat messages are limited per client IP (`CHAT_MESSAGES_PER_MINUTE`).

## API

All endpoints return JSON except the chat stream (`text/event-stream`). `POST`/`PATCH`/`DELETE` requests need
the `X-CSRF-Token` header returned by `GET /api/session`.

| Method & path | Description |
|---|---|
| `GET /api/session` | CSRF token for this server run |
| `GET /api/health` | `ok` / `degraded` (database + ingestion worker) |
| `GET/POST /api/conversations` | List / create conversations |
| `GET/PATCH/DELETE /api/conversations/{id}` | Read with messages / rename / delete |
| `POST /api/conversations/{id}/messages` | `{content}` → SSE: `start`, `sources`, `delta`…, `done` or `error` |
| `POST /api/conversations/{id}/regenerate` | Re-answer the last question (SSE) |
| `GET /api/admin/overview`, `/api/admin/health` | Dashboard metrics and service checks |
| `GET/POST /api/admin/documents` | List (`?q=&status=`) / upload (multipart field `files`) |
| `GET/DELETE /api/admin/documents/{id}` | Details with logs and chunk preview / delete |
| `POST /api/admin/documents/{id}/reindex`, `POST /api/admin/reindex` | Reindex one / all |
| `GET /api/admin/knowledge-base`, `GET /api/admin/events` | Index configuration / ingestion log |

## Tests

```powershell
python -m unittest discover -s tests
```

The suite starts a real server on a random port with a stub LLM. It covers CSRF and cross-origin blocking,
upload validation and path traversal, the upload → index → chat → citation → delete cycle, failed ingestion,
reindexing, conversation history,
regenerate, friendly model errors, legacy index import, and the streaming parsers for all three LLM providers.

## Production deployment

### Vercel

The repository includes `api/index.py` and `vercel.json`, so it can be imported directly into Vercel. The
deployment uses Vercel's Python runtime and needs no build command. Add the `LLM_*` variables in the Vercel
project settings if generated answers are required; without them, the app runs in retrieval-only mode.

Vercel Functions have instance-local temporary storage. The bundled vector index is loaded on each cold start,
but conversations, uploads, and changes made in the admin dashboard are temporary and may differ between
instances. For a durable multi-user production deployment, replace SQLite and the local document/vector files
with managed database, object storage, and vector-store services (or deploy this application on an always-on
host with a persistent disk).

For an always-on deployment with persistent local storage:

1. Set `APP_ENV=production` and configure the LLM/embedding variables in `.env` (or real environment variables).
2. The app has no login, so if other people need access, run it on localhost behind an HTTPS reverse proxy
   that **authenticates** users. Set `TRUST_PROXY=true`. Example Caddyfile with basic auth:

   ```text
   assistant.example.com {
       basic_auth {
           team <hash from: caddy hash-password>
       }
       reverse_proxy 127.0.0.1:8000 {
           flush_interval -1   # stream answers without buffering
       }
   }
   ```

   With nginx, also set `proxy_buffering off;` for `/api/conversations/`.
3. Run it as a service (systemd, NSSM on Windows, or a container) that restarts on failure. `SIGTERM` shuts down cleanly.
4. Point monitoring at `GET /api/health`. It returns 503 when the database or ingestion worker is down.
5. Keep `storage/` on persistent disk.

### Backup and recovery

```powershell
python manage.py backup --output backups
```

This writes a consistent copy of the SQLite database (using SQLite's online backup), `vectors.json`, and the original
uploaded files to a timestamped folder. It's safe to run while the server is up. Schedule it daily and copy backups
off the machine. To restore, stop the server, copy the three items back to the paths in `.env`, and start it. On
startup the app reconciles the database with the index: it re-queues interrupted jobs, removes orphaned chunks, and
marks documents whose chunks are missing as failed so they can be reindexed.

### Legacy command-line tools

`python -m vectorstore.stats` still works. `python -m vectorstore.documents delete` edits the vector file
directly. Prefer the admin dashboard, which keeps the database and the index in sync. Never use the CLI while the
server is running.

## Known limitations

- **No accounts.** Everyone shares one workspace, sees the same conversations, and can manage documents.
- **Single process.** The vector index and rate limits live in one process's memory. Run one
  instance per storage folder. Horizontal scaling needs a shared vector database (pgvector, Qdrant) and a shared
  rate limiter.
- **Standard-library HTTP server.** It's thread-per-connection with request timeouts and size limits, and is
  suitable for small teams behind a reverse proxy. For high traffic or public internet exposure without a proxy,
  move the HTTP layer to an ASGI server. The services are framework-independent.
- **JSON vector store.** The whole index is held in memory and the file is rewritten on each change. That's fine
  up to tens of thousands of chunks; beyond that, use a dedicated vector database.
- **Local hash embeddings are keyword matching, not semantic search.** Configure `EMBEDDING_MODEL` for questions
  phrased differently from the documents.
- **Imported legacy documents** (indexed before this version) have no original file. Reindexing re-embeds their
  stored text, which is enough for embedding changes but not for chunking changes. Re-upload them for that.
- **Stop button.** The server stops generating as soon as it detects the closed connection. Some browsers take a few
  seconds to close an aborted stream, so the model may keep generating briefly.
- **Gemini latency.** During testing, Gemini sometimes took 25–200 s or returned 503 (overloaded).
  `LLM_THINKING_LEVEL=low` and a 30 s timeout help; a faster provider helps more.
