# Pollution Tracker — Backend

Municipal pollution reporting workflow: **detect → assign → verify**.
FastAPI + PostgreSQL, containerized with Docker.

## What's actually been tested vs. what hasn't

Being upfront about this so nobody assumes more than what's true:

- ✅ **Verified working**: the full FastAPI application, running against a
  real PostgreSQL 16 database (not mocked), was tested end-to-end —
  photo upload, mock classification, duplicate/cluster detection,
  severity scoring, status updates, and before/after verification all
  confirmed working with real HTTP requests and real database rows.
  One real bug (stale severity score on the 3rd report in a cluster)
  was caught during this testing and fixed — see the comment in
  `app/routers/reports.py` if you're curious what happened.
- ⚠️ **Not run in this environment**: `docker compose up` itself, because
  Docker isn't available in the sandbox this was built in. The
  Dockerfile and docker-compose.yml were carefully reviewed by hand —
  one real bug was caught this way too (a missing-.env crash) and
  fixed — but you should still treat your team's first `docker compose
  up` as the real first run and tell me immediately if anything about
  it doesn't match what's described here.

## Prerequisites

- Docker Desktop installed and running (includes Docker Compose)
- That's it — you do NOT need Python or PostgreSQL installed locally,
  Docker handles both.

## First-time setup (do this before opening VS Code)

```bash
# 1. Copy the environment template. Do this FIRST — several things
#    (Docker Compose, VS Code's debugger) expect .env to exist.
cp .env.example .env

# 2. Start everything (Postgres + API)
docker compose up --build
```

That's it. On first run, this will:
- Pull the `postgres:16-alpine` image and start a database
- Build the API image from the Dockerfile
- Wait for Postgres to report healthy (via the healthcheck) before starting the API
- Create the database tables automatically
- Start the API on **http://localhost:8000**

You'll see a warning in the logs about running in MOCK classification
mode — that's expected until you add a Gemini API key (see below).

**Interactive API docs**: http://localhost:8000/docs — this is
auto-generated from the code and lets you try every endpoint from your
browser without writing any frontend code first. Good place to start if
you're on the frontend team and want to see what you're working with.

## Getting a Gemini API key (when you're ready)

1. Go to **aistudio.google.com**
2. Sign in with a Google account
3. Click "Get API key" — free tier is enough for hackathon usage
4. Open `.env` and set `GEMINI_API_KEY=your_key_here`
5. Restart: `docker compose restart api`

No code changes needed — the classifier automatically switches from mock
to real the moment the key is present. See `app/services/classifier.py`
and `app/services/verification.py` if you want to see how that switch
works.

## Project structure

```
app/
  main.py              # Entry point — wires everything together
  core/
    config.py          # ALL settings live here — env vars, weights, thresholds
    database.py         # DB connection setup — don't touch unless you know why
  models/
    report.py           # SQLAlchemy tables: Cluster, Report
  schemas/
    report.py           # Pydantic request/response shapes — the API contract
  routers/
    reports.py           # Core loop: upload, list, status update
    verification.py     # Before/after verification endpoint
  services/
    classifier.py        # Gemini image classification (mock/real switch)
    verification.py     # Gemini before/after comparison (mock/real switch)
    clustering.py         # Duplicate detection (geo-distance + time window)
    severity.py           # Severity scoring + department routing
    storage.py            # Photo file storage

.vscode/               # Team-wide editor config — see below
api-tests.http          # Pre-written API test requests (see below)
test-assets/            # Sample images for testing uploads
docker-compose.yml
Dockerfile
```

**If you're adding a new feature**, it almost certainly touches:
1. `models/report.py` (if it needs new data)
2. `schemas/report.py` (if the API shape changes)
3. A new or existing file in `services/` (the actual logic)
4. A new or existing file in `routers/` (the endpoint)

Try to keep logic OUT of routers — routers should mostly call a service
function and return the result. This makes things testable and means
two people can work on a router and its service function somewhat
independently.

## VS Code setup

Open this folder in VS Code. You'll get a popup: **"This workspace has
extension recommendations"** — click **Install All**. This gets everyone
on the same formatter, the same debugger, and the same REST client
without a setup conversation.

### Running the debugger (do this instead of print statements)

1. Set a breakpoint by clicking just left of a line number in any route
   handler (e.g. `app/routers/reports.py`)
2. Go to the Run and Debug panel (the play-button-with-a-bug icon in the
   left sidebar)
3. Select **"Debug FastAPI (uvicorn)"** from the dropdown at the top
4. Press the green play button
5. Send a request that hits your breakpoint (use `api-tests.http` — see
   below) — execution will pause and you can inspect every variable

This matters more than it might seem: with a debugger, "why is this
returning the wrong value" takes 30 seconds to answer. With print
statements, it can take 10 minutes of edit-save-restart cycles — time
you don't have this week.

### Testing endpoints without writing frontend code

Open `api-tests.http`. You'll see **"Send Request"** appear above each
request when you have the REST Client extension installed. Click it,
and the response shows up in a split pane. This is how the backend pair
should sanity-check their own work before the frontend pair integrates
against it.

## Common commands

```bash
# Start everything
docker compose up

# Start in the background (so your terminal is free)
docker compose up -d

# View logs when running in the background
docker compose logs -f api

# Stop everything
docker compose down

# Stop AND wipe the database (start completely fresh)
docker compose down -v

# Rebuild after changing requirements.txt (not needed for app/ code changes — those reload live)
docker compose up --build
```

## Troubleshooting

**"Connection refused" or the API won't start:**
Check `docker compose logs api` — the most likely cause is Postgres not
being ready yet, but the `depends_on: condition: service_healthy` setting
should already handle that. If it still happens, run `docker compose down
-v` and `docker compose up --build` fresh.

**Port 5432 or 8000 already in use:**
Something else on your machine is using that port. Either stop it, or
change the left-hand side of the port mapping in `docker-compose.yml`
(e.g. `"5433:5432"`) — just remember to update `DATABASE_URL` in `.env`
to match if you do this for Postgres.

**Code changes aren't showing up:**
The `app/` folder is mounted live (see the `volumes:` section in
`docker-compose.yml`), so changes should reload automatically via
uvicorn's `--reload` flag. If they genuinely don't, try `docker compose
restart api` before reaching for a full rebuild.

**VS Code says it can't find installed packages / autocomplete is broken:**
Bottom-left corner of VS Code should show a Python interpreter. If it's
not pointing at this project, you likely need to run the app outside
Docker once to create a local `venv/` for VS Code to point at:
```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```
Then in VS Code: Cmd/Ctrl+Shift+P → "Python: Select Interpreter" →
choose the one at `./venv/bin/python`.
