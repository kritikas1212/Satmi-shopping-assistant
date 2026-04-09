# SATMI Frontend (Next.js + Firebase Auth)

This workspace is a production-ready chat frontend for the SATMI FastAPI + LangGraph backend.

## Features

- Google Sign-In via Firebase Authentication
- `user_id` sourced from Firebase UID (falls back to guest id)
- Stable `conversation_id` generated once per session
- `Authorization: Bearer <idToken>` sent to `POST /chat`
- Async queue polling for `GET /tasks/{task_id}` every 2 seconds
- Markdown rendering for bot replies (including lists and tables)
- Responsive Tailwind UI tuned for SATMI brand tone

## 1) Configure Environment

Copy the example file and fill values:

```bash
cp .env.local.example .env.local
```

Required values in `.env.local`:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
NEXT_PUBLIC_FIREBASE_API_KEY=...
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=...
NEXT_PUBLIC_FIREBASE_PROJECT_ID=...
NEXT_PUBLIC_FIREBASE_APP_ID=...
```

Optional when backend auth is enabled with shared API key:

```env
NEXT_PUBLIC_SATMI_API_KEY=...
```

## 2) Firebase Setup (Google Login)

In Firebase Console:

1. Create/select project.
2. Enable Authentication -> Sign-in method -> Google.
3. Add Web App and copy config keys.
4. Add localhost domains in Authentication -> Settings -> Authorized domains:
	- `localhost`
	- `127.0.0.1`

## 3) Run Locally

```bash
npm install
npm run dev
```

Open `http://localhost:3000`.

## 4) Backend Expectations

Your FastAPI backend should be running at `NEXT_PUBLIC_API_BASE_URL` and expose:

- `POST /chat`
- `GET /tasks/{task_id}`

If backend returns `metadata.async_task_id`, frontend auto-polls task status and renders completion/failure.

## 5) Production Notes

- Keep Firebase credentials in environment variables only.
- Do not commit `.env.local`.
- For CORS in backend, allow your frontend production domain.
- If `/tasks/{task_id}` is support-role restricted, expose a user-safe task status endpoint or relax role check for self-owned tasks.
