# Templates

Page templates for *New page* live here as ordinary Markdown, one
`<name>.md` file each, with a lowercase kebab-case name. An optional
frontmatter block sets `title` and `description` (what the picker shows) and
`kind: note` or `kind: decision` (a decision template starts a proposal).
The body is the new page's starting text; `{{date}}` becomes the day the
page is created. A file named like a built-in template (`meeting-notes`,
`how-to`, `decision`, `requirement`, `plan`) replaces it. Templates are not
records: they are not indexed or linted.
