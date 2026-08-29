# Projects

Durable project-scoped records live here as metadata-bearing Markdown. Each
project scope requires exactly one usable overview at
`projects/<project-id>.md` with `id: <project-id>`, `type: project`, and
`scope: project:<project-id>`; its status must be `draft` or `active`.
`kos lint` enforces this identity invariant before context is requested.
