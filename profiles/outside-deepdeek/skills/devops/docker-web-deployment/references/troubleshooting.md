# Troubleshooting Reference

## Error: "unable to open database file" in Docker

Full trace:
```
sqlite3.OperationalError: unable to open database file
  File "/app/api/dashboard.py", line 22, in get_dashboard
    active_events=db.execute(...)
```

**Verified state**: DB file exists, mounted correctly, permissions OK (root can read), `ls /data/` shows file inside container.

**Root cause**: SQLite WAL mode. When a database was previously opened in WAL mode (journal_mode=wal), SQLite tries to create `-wal` and `-shm` files on every connection. With a read-only Docker volume mount (`:ro`), file creation fails with a cryptic "unable to open database file" error instead of a clear permission error.

**Fix**: `sqlite3.connect("file:/data/db.sqlite?mode=ro&immutable=1", uri=True)`

## Error: npm ci cross-platform failure

```
npm error code EUSAGE
npm ci can only install packages when lockfile matches
```

**Root cause**: `package-lock.json` generated on Windows contains platform-specific optional dependencies. Running `npm ci` on Alpine Linux fails because those Windows-only packages don't exist.

**Fix**: Use `npm install --legacy-peer-deps` instead of `npm ci` in Dockerfile.

## Error: Tailwind v4 @apply in Docker build

```
Error: Cannot apply unknown utility class `border-border`
Error: Cannot apply unknown utility class `bg-background`
```

**Root cause**: Tailwind v4 `@theme inline` variables aren't fully recognized by the `@apply` directive in some build environments.

**Fix**: Replace `@apply` with raw CSS using `var(--token-name)`.

## Error: useSearchParams() prerender failure

```
Error occurred prerendering page "/events"
Export encountered an error on /events/page: /events, exiting the build
```

**Root cause**: `useSearchParams()` requires a `<Suspense>` boundary in Next.js App Router.

**Fix**: Wrap the component using `useSearchParams` in `<Suspense>`:
```tsx
export default function Page() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <InnerComponent />  {/* uses useSearchParams */}
    </Suspense>
  );
}
```

## Error: Next.js SSR fetch fails in Docker

**Symptom**: Page shows "API unavailable" but `curl localhost:80/api/v1/...` returns JSON correctly.

**Root cause**: Server Components do SSR. During SSR, `fetch("/api/v1/...")` resolves to `http://frontend-container:3000/api/v1/...`. The frontend container doesn't have the API — it's on the backend container at port 8000.

**Fix**: Make data-fetching pages Client Components. The browser-side `fetch("/api/v1/...")` resolves through nginx → backend correctly.
