# Video Downloader

موقع تحميل فيديوهات عالمي يدعم أكثر من 1800 منصة (YouTube, TikTok, Facebook, Instagram, Twitter/X, وغيرها) باستخدام yt-dlp.

## Run & Operate

- `python artifacts/api-server/app.py` — run the Python Flask API server (port 8080)
- `pnpm --filter @workspace/video-downloader run dev` — run the React frontend dev server
- `PORT=8080 BASE_PATH=/ NODE_ENV=production pnpm --filter @workspace/video-downloader run build` — production build of frontend
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from the OpenAPI spec
- `pnpm run typecheck` — full typecheck across all packages

## Stack

- **Frontend**: React 19 + Vite 7 + Tailwind CSS 4, served via pnpm monorepo (`@workspace/video-downloader`)
- **Backend**: Python 3.11 + Flask 3 + yt-dlp — serves both the API and the built React static files in production
- **API contract**: OpenAPI 3.1 → Orval codegen → `@workspace/api-client-react` (React Query hooks + Zod schemas)
- **Production server**: Gunicorn (WSGI) via `wsgi.py` at the project root

## Where things live

| Path | Purpose |
|---|---|
| `artifacts/api-server/app.py` | Flask backend — all API routes + static file serving |
| `artifacts/video-downloader/src/pages/home.tsx` | Single-page React UI |
| `lib/api-spec/openapi.yaml` | OpenAPI spec (source of truth for API contract) |
| `lib/api-client-react/src/generated/` | Auto-generated hooks & schemas (do not edit manually) |
| `wsgi.py` | Gunicorn entry point for production |
| `build.sh` | Render build script (installs Node + pnpm + builds frontend + installs Python deps) |
| `render.yaml` | Render deployment configuration |
| `requirements.txt` | Python dependencies (root level, used by Render) |

## Architecture decisions

- **Single service on Render**: Flask serves both the `/api/*` routes and the built React static files from `artifacts/video-downloader/dist/public/`. This avoids CORS issues and simplifies deployment to a single Render web service.
- **Static serving is conditional**: The catch-all React Router route in `app.py` is only registered when `dist/public/index.html` exists. In Replit dev mode, Vite handles the frontend; in production, Flask serves it.
- **gunicorn via wsgi.py**: The `api-server` directory name contains a hyphen which is not a valid Python import identifier, so `wsgi.py` at the project root adds the correct path to `sys.path` before importing `app`.
- **Vite build requires PORT + BASE_PATH**: `vite.config.ts` throws if these env vars are missing. The `build.sh` always sets `PORT=8080 BASE_PATH=/ NODE_ENV=production` before running the Vite build.
- **yt-dlp is Python-native**: No subprocess calls — yt-dlp is imported directly as a Python library, which is faster and more reliable than calling the CLI binary.

## Product

Paste any video URL → get direct download links for the best available video quality and audio-only format. Supports 1800+ platforms via yt-dlp. Optional `cookies.txt` (Netscape format) placed at `artifacts/api-server/cookies.txt` unlocks age-restricted or login-required content. Optional `PROXY` env var for geo-restricted content.

## Render deployment

1. Push this repo to GitHub.
2. On Render → New Web Service → connect the repo.
3. Render auto-detects `render.yaml` and configures the service (Python runtime, `./build.sh` build command, gunicorn start command).
4. No extra environment variables are required for basic operation.
5. Optional env vars:
   - `PROXY` — HTTP proxy URL for geo-restricted content
   - `FRONTEND_DIST` — override the path to the built React files (default: auto-detected)

## Gotchas

- **pnpm-workspace.yaml esbuild overrides**: all non-linux-x64-gnu binaries are excluded. This is intentional (Replit + Render both run linux-x64-gnu). Do not remove the overrides.
- **minimumReleaseAge: 1440** in pnpm-workspace.yaml: packages must be 1 day old before pnpm installs them. The build.sh uses `--no-frozen-lockfile` to avoid lockfile conflicts.
- **Replit-specific Vite plugins** (cartographer, dev-banner): only loaded when `REPL_ID` is set AND `NODE_ENV !== production` — safe to ignore in production.
- **dist/ is gitignored**: the React frontend is rebuilt from source on every Render deploy by `build.sh`.

## User preferences

- Backend must use Python Flask + yt-dlp (not Node.js child_process).
- UI language: bilingual Arabic/English with RTL support.
- No emoji in the UI.
- Deployment target: Render (single web service).
