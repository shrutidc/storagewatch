# StorageWatch

A macOS filesystem observability platform for monitoring AI infrastructure storage.

## Quick Start

### Prerequisites
- **Python 3.10+** (the backend uses `X | Y` type annotations, which raise
  `TypeError` on 3.9)
- Node.js 18+
- macOS (the collector reads `diskutil` / `fdesetup` / `tmutil`)
- Access to: Tiger Data, Auth0, Backboard

### One-time Auth0 setup

The backend verifies access tokens, which Auth0 only issues as verifiable JWTs
when the request names a registered API. In the Auth0 dashboard:

1. **Applications → APIs → Create API**, identifier exactly `storagewatch-api`,
   signing algorithm RS256.
2. **Applications → your SPA → Settings → Application URIs**: add
   `http://localhost:3000` to Allowed Callback URLs, Logout URLs and Web Origins.

Without step 1, Auth0 returns an opaque token and every API call returns 401.

### Setup

1. **Environment files** — there are two, and both are required:
   ```bash
   cp .env.example .env                     # backend + collector
   cp frontend/.env.example frontend/.env   # frontend (Vite reads VITE_* here only)
   ```
   Fill in `TIGER_DATABASE_URL`, `AUTH0_DOMAIN`, `AUTH0_AUDIENCE`,
   `BACKBOARD_API_KEY`, and generate the collector's shared secret:
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # -> AGENT_TOKEN
   ```
   `AUTH0_AUDIENCE` and `VITE_AUTH0_AUDIENCE` must match.

2. **Python dependencies:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Run all three, each in its own terminal** (they are long-running):
   ```bash
   cd backend   && python main.py      # :8000
   cd frontend  && npm install && npm run dev   # :3000
   cd collector && python collector.py
   ```

Dashboard at `http://localhost:3000`.

### Production build

For deployment the backend serves the built dashboard itself, so the browser
talks to a single origin and `/api` needs no CORS or proxy (Vite's dev proxy
only exists under `npm run dev`):

```bash
cd frontend && npm run build     # -> frontend/dist
cd ../backend && python main.py  # serves the dashboard and the API on one port
```

The whole app is then on `:8000`. The host's `PORT` variable is honoured if set.
The collector still runs on the monitored Mac, with `BACKEND_URL` pointing at
the public URL.

### Authentication

| Caller | Credential |
|---|---|
| Dashboard (browser) | Auth0 access token, verified against the tenant's JWKS |
| Collector agent | `AGENT_TOKEN` shared secret — it runs unattended with no user to sign in as |

The backend refuses to start if `AUTH0_DOMAIN`, `AUTH0_AUDIENCE` or
`AGENT_TOKEN` is missing, rather than serving telemetry unprotected.

## Architecture

```
Mac Agent (collector) → FastAPI Backend → Tiger Data
                                      ↓
                              React Dashboard ← Auth0
                                      ↑
                                 Backboard (AI)
```

## Project Structure

```
storagewatch/
├── collector/          # Python agent (runs on Mac)
├── backend/            # FastAPI server
├── frontend/           # React dashboard
├── requirements.txt    # Python dependencies
└── README.md
```

## Development

See detailed PRDs in the onboarding doc for Person A (Backend) and Person B (Frontend).

## Demo Flow

1. Collector samples filesystem metrics every 5 seconds
2. POST metrics to FastAPI backend
3. Backend stores in Tiger Data and detects anomalies
4. Dashboard queries current + historical metrics
5. Alert triggers if anomaly detected
6. "Explain with AI" calls Backboard for analysis
