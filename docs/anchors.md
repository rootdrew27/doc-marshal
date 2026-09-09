---
type: reference
updated: 2026-09-08
summary: "Anchor fields: how entries resolve, which ones a change is matched against, and what every path entry must satisfy"
code_refs:
  - src/doc_marshal/ontology.py
  - src/doc_marshal/anchors.py
  - src/doc_marshal/drifted.py
---

# Anchor fields

An anchor is a frontmatter field naming what outside a note would falsify it. Anchor fields are
declared by the profile, not fixed in the engine: an `AnchorField` carries a name, what it holds,
and a `resolves` tuple saying what its entries may be. The engine reads `resolves` and nothing else
about the field.

## How entries resolve

| `resolves` | An entry is | Matched against a change |
| --- | --- | --- |
| `repo-path` | a path from the repository root that exists and is tracked | yes |
| `docs-path` | a path from the repository root that resolves inside the docs tree | yes |
| `url` | an `http://` or `https://` address | no |
| `opaque` | any non-empty value | no |

A field may name several: an entry is valid when any of them accepts it. The
[standard profile](standard-profile.md) declares two, `code_refs` as `repo-path` and `source` as
`docs-path` or `url`; `doc-marshal info --policies` renders the table of what each holds and which
types must carry it, from the profile itself.

`repo_path_fields` is the set that resolves as `repo-path` -- the code anchors, and what the
warning about a `done` spec reads. `path_fields` is wider: every field whose entries may be
repository paths, code anchors and `docs-path` fields alike. `doc-marshal drifted` matches
`path_fields`, so a note whose source note or asset changed is reported too.

No ontology is required to declare a `repo-path` field. A profile whose fields are all `opaque` is
legal, and `drifted` says that no field resolves as a path rather than reporting nothing.

## What every path entry must satisfy

Checked by `resolve_entry` in `anchors.py`, whichever field holds the entry:

- Written from the repository root. Absolute is an error, and so is any `.` or `..` segment.
- Spelled exactly as the filesystem has it. Existence is read from real directory listings, so a
  case-insensitive filesystem cannot pass a path that CI will fail on.
- Naming something strictly inside the repository. The repository root itself is not an anchor: a
  note anchored to everything is anchored to nothing. A directory is fine, and anchors every file
  beneath it.
- Tracked by git. A path that exists only in this checkout satisfies the anchor nowhere else.
  Outside a git repository every path entry is an error.
- A `docs-path` entry must additionally resolve inside the docs tree; code paths belong in a
  `repo-path` field, and accepting one here would let a note satisfy its minimum while naming no
  code.

An anchor field's value is a list. A scalar is an error, and every consumer reads a scalar as
anchoring nothing rather than iterating its characters.

## Minimums, not permitted sets

`requires` is the set of fields of which a note must carry at least one, and `requires_from` is the
status from which that binds. Any declared field is legal on any type and is validated whenever it
is present, required or not.

## What `drifted` matches

`doc-marshal drifted` reads every entry of every `path_fields` field, skips the URLs, and reports a
note when one of its entries is, contains, or lies under a changed path -- containment counts in
both directions, so a coarse anchor and a fine one surface the same way. The change is the branch's
own commits plus uncommitted work by default, an explicit `--range A..B`, or paths given directly
with `--paths`.

Its exit status is 0 whether or not anything matched: a drifted note is a prompt to look, not a
verdict. `--fail-on-match` inverts that for a pre-merge check that wants the build to stop.
