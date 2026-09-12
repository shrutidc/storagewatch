# StorageWatch

A macOS filesystem observability platform for monitoring AI infrastructure storage.

## Quick Start

### Prerequisites
- Python 3.9+
- Node.js 18+
- Access to: Tiger Data, Auth0, Backboard API

### Setup

1. **Clone and setup environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your Tiger Data, Auth0, and Backboard credentials
   ```

2. **Backend (Python):**
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   cd backend && python main.py
   ```

3. **Frontend (React):**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

Dashboard will be at `http://localhost:3000`

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
