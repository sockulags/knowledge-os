# Projects

Each project owns one directory at `projects/<project-id>/`. Its required
overview is `projects/<project-id>/README.md` with `id: <project-id>`, `type:
project`, and `scope: project:<project-id>`; its status must be `draft` or
`active`. Every other project record with that scope also stays below the same
project directory.

Inside a project directory, folders may use any safe filesystem name and nest
to any depth. A folder may have its own metadata-bearing `README.md` root
record; other records retain the normal `<id>.md` filename. IDs remain globally
unique. `kos capture --project-path PATH` creates a project record at an
explicit path relative to its project directory and creates missing parent
folders. `kos lint` enforces containment and the overview identity invariant.
Project decision records use the same explicit acceptance and supersession
contract as general decisions. A draft replacement does not retire its active
target; only `kos supersede` performs that coordinated transition.
