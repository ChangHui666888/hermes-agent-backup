# Docker Deployment Pitfalls — Complete Reference

## Symptom → Root Cause → Fix

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| API unavailable in browser | NEXT_PUBLIC_API_URL not inlined at build time, falls back to localhost | Set ENV in Dockerfile BEFORE COPY+BUILD; set env block in next.config.ts; hardcode /api/v1 in api.ts fallback |
| 502 Bad Gateway after frontend rebuild | Nginx caches upstream container IP. Rebuilding frontend creates new container with new IP. | `docker compose restart nginx` after any frontend rebuild |
| sqlite3.OperationalError: unable to open database file | WAL mode needs write access on read-only Docker volume mount | Use `file:...?mode=ro&immutable=1` URI with `uri=True` |
| useSearchParams prerender error | Server Component using client-side hook; Next.js tries to SSR it | Wrap in Suspense boundary, or make entire page client component |
| Server Component SSR fetch fails (page shows API error in browser) | fetch() inside async Server Component resolves against frontend container (port 3000, no API). API is on backend container (port 8000) | Convert page to client component: add "use client", use useEffect + fetch on mount |
| Tailwind v4 @apply errors (border-border, bg-background) | @apply with shadcn's generated utility classes incompatible with Tailwind v4's CSS-first approach | Replace @apply directives with vanilla CSS: `background-color: var(--background)` instead of `@apply bg-background` |
| `npm ci` fails on Alpine | Platform-locked package-lock.json | Use `npm install --legacy-peer-deps` instead |

See `references/sqlite-readonly-docker.md` for the full 10-issue pitfalls reference.

| TypeScript type errors on third-party modules (react-simple-maps) | Missing @types declarations in Docker build context | Set `typescript: { ignoreBuildErrors: true }` in next.config.ts |
| Cloud server crashes during --no-cache build | Full Next.js rebuild + npm install exhausts RAM (3.9GB on typical VPS) | Never use --no-cache. For stale builds, do: rm -rf .next inside container, then incremental rebuild |
| Backend health check never passes (health: starting forever) | DB_PATH env not set or SQLite file not mounted | Verify volume mount: docker exec container ls /data/; verify env: docker exec container env | grep DB_PATH |
