# Teleprompt

This repo is configured for free hosting + auto deploy:
- `frontend` -> Vercel (Hobby/free)
- `backend` -> Render (Free Web Service)
- CI/CD -> GitHub Actions (`.github/workflows`)

## Local Development

Frontend:
```bash
cd frontend
cp .env.example .env.local
npm ci
npm run dev
```

Backend:
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## One-Time Production Setup

1. Create a Render Web Service from this repo:
- Runtime: `Python`
- Root Directory: `backend`
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Free plan
- Optional env var: `TELEPROMPT_WHISPER_MODEL=base.en`

2. Create a Vercel project from this repo:
- Root Directory: `frontend`
- Framework: Next.js
- Add env var `NEXT_PUBLIC_BACKEND_URL` = your Render URL (example: `https://teleprompt-backend.onrender.com`)

3. Create deploy hooks:
- Render: Service Settings -> Deploy Hook
- Vercel: Settings -> Git -> Deploy Hooks

4. Add GitHub repository secrets:
- `RENDER_DEPLOY_HOOK_URL`
- `VERCEL_DEPLOY_HOOK_URL`

## CI/CD Flow

1. Push to `main` (including pushes made from Codex).
2. GitHub Actions runs `CI`:
- frontend lint/build
- backend syntax compile
3. If CI passes, `Deploy` workflow triggers both deploy hooks.
4. Render and Vercel pull latest code and redeploy automatically.

## Files Added For This

- `.github/workflows/ci.yml`
- `.github/workflows/deploy.yml`
- `render.yaml`
- `frontend/.env.example`
