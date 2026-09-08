---
type: reference
updated: 2026-09-07
summary: The three blocks a fresh session is handed about the docs tree, and what the plugin's SessionStart hook does with them
code_refs:
  - src/doc_marshal/briefing.py
  - plugin/hooks/session-start.py
---

# The briefing

`doc-marshal briefing` prints what a fresh session is given about the docs tree: three blocks, in
the order they should be read, separated by blank lines. The engine decides the content; wiring it
to a harness's session-start event is the plugin's job.

## The three blocks

| Block | What it holds |
| --- | --- |
| index preview | the docs tree's path, the note count, and one entry per folder with its own count -- then a pointer to `INDEX.md` for the full list and the reminder that it is generated |
| the shared vocabulary | the root `NOMENCLATURE.md` as content: one line per term, then its remaining sections as written |
| the types | one line per live type -- what it serves and what it must carry -- under a sentence pointing at `doc-marshal info <type>`, `info --marshalling` and `new` |

The index preview is a uniform reduction at every size, the top level included. `INDEX.md` grows
linearly with the tree forever, and a summary of every note is a cost every session pays whether or
not it opens a note; a session that needs to route to one spends a single tool call instead.

Two conditions are folded into the first block. A stale index -- the notes no longer matching what
`index` would generate -- puts a warning ahead of the preview, because a session routing off a
stale index is exactly when staleness matters. Notes that could not be indexed are listed after it.
Any failure to answer counts as not stale: a broken hook must not manufacture a warning about the
docs.

## The vocabulary as content

The vocabulary note is read through the same table parser the validator uses, so a reformatted
table cannot leak in as raw text. Each row becomes the term in bold, its definition, then each
scanned column under its own name -- for `standard`, the aliases the term rules out. The other
sections follow as written. Frontmatter, the H1 and HTML comments are not emitted: they are for
the validator and the author.

The terms and the aliases each of them rules out are the content, not a summary of them; a summary of a
vocabulary is a second vocabulary. Only the root note is briefed. A nested one governs its subtree
and is read on arriving there. When the root note is absent, the block says so and gives the
`doc-marshal new` command that scaffolds it. When its table is not the shape the profile expects,
the body is emitted verbatim rather than hidden -- the malformed table is `check`'s finding to
report.

## `--quiet-if-absent`

With `--quiet-if-absent` the command prints nothing and exits 0 when no docs tree resolves, rather
than failing. That is for a hook installed across every project, most of which have no docs tree.

## The SessionStart hook

`plugin/hooks/session-start.py` is deliberately thin. It resolves the project's own engine the way
every [integration](integrations.md) does, runs `briefing --quiet-if-absent`, and writes the output
as the `additionalContext` of a `SessionStart` hook result. It stays silent when the command fails, when the output is empty, and on any internal
failure of its own.

The one thing it says on its own is `MISSING_ENGINE`: the project has a `.doc-marshal.toml` but no
engine was found, so notes are not being validated as they are written. Silence there would look
like a clean tree. Because it arrives as `additionalContext`, it is read by an agent at the top of
a session opened for unrelated work, so it states the situation and stops: it says this is context
rather than a task, and that the version to install is the one the repository already names --
never the latest release, which would leave the engine disagreeing with every
[jurisdiction](jurisdictions.md) here.
