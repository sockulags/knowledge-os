# Knowledge OS Reader UI

A React single-page app (Vite, TypeScript, Tailwind CSS v4) for the
Knowledge OS Reader. It renders finished sentences and HTML the Python API
(`knowledge_os/reader/api/`) sends; it never re-derives trust, lifecycle, or
grouping rules of its own.

## Develop

```
npm install
npm run dev
```

`npm run dev` starts Vite on its own port and proxies `/api/*` requests to a
Python server at `http://127.0.0.1:8800` (see `vite.config.ts`). Start that
server separately, from the repository root:

```
kos-read --root . --port 8800
```

Write requests (`POST /api/records`, `PATCH /api/records/{id}`) work the same
way in dev mode and in the desktop app: fetch `GET /api/session` once, then
send its `write_token` in the `X-KOS-Write-Token` header with a JSON body. The
core accepts writes only from a loopback `Host` and `Origin`, so the Vite page
on `http://localhost:5173` is allowed and a page on any other site is not. The
endpoints are documented in "Local interface write API" in
[`docs/architecture.md`](../docs/architecture.md).

## Build

```
npm run build
```

Runs `tsc -b` (strict type checking) and then `vite build`, which writes the
production bundle to `../knowledge_os/reader/static/app/`. That output is
committed to the repository so `pip install -e ".[reader]"` and `kos-read`
work with no Node toolchain installed — rebuild and commit it whenever this
directory changes.
