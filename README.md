# Real-time Chat Application (Polished)

A modern real-time chat app built with React (Vite) and Flask-SocketIO.

## What's new
- ✅ Clean, complete backend without placeholders
- ✅ Typing indicators
- ✅ Read receipts (shows "read by: ...")
- ✅ Room switching (general, random, tech-talk)
- ✅ Health check endpoint at `/health`
- ✅ `VITE_BACKEND_URL` support for frontend
- ✅ Dockerized (frontend + backend)
- ✅ One-command local dev (`npm run dev` from repo root)

## Quick start (local, no Docker)

```bash
# 1) Backend
python -m venv .venv && . .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -r backend/requirements.txt
python backend/app.py

# 2) Frontend (new terminal)
cd frontend
npm install
npm run dev
```

Open: http://localhost:5173  (Frontend)
Backend: http://localhost:5000

> If your backend runs elsewhere, set `VITE_BACKEND_URL` in `frontend/.env`:
>
> ```env
> VITE_BACKEND_URL=http://localhost:5000
> ```

## Docker

```bash
cp .env.example .env
docker compose up --build
```

Then open http://localhost:5173

## Env vars
- Backend: see `backend/.env.example`
- Frontend: `VITE_BACKEND_URL`

## Scripts

```bash
npm run install-all  # install backend + frontend deps
npm run dev          # run both servers
npm run dev:backend
npm run dev:frontend
npm run build        # build frontend
```

## Notes
- In-memory storage is used for messages and presence (fits demo/dev). For production, connect a database and persist messages.
- CORS is open for local dev; tighten for production.
- Read receipts are per-message and show names that have seen the message.
- Typing indicator disappears after ~1.5s.
- Health endpoint returns `{ ok: true }`.
