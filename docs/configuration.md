---
type: spec
updated: 2026-10-13
summary: "The config folder: config.toml declares the anchor fields, one file per type in types/, and what a broken config does"
status: in-progress
code_refs:
  - src/doc_marshal/config.py
---

# Configuration

## Overview

A docs tree's config is the folder `.doc-marshal/` at its top, and it is the whole profile the
tree's notes are held to. `init` writes the `standard` profile into it; from then on the tree's own
files are the profile. `load_profile` in `src/doc_marshal/config.py` reads it.

```
.doc-marshal/
  config.toml       # marks the docs tree; declares the anchor fields
  types/
    reference.toml  # one file per type
```

## Behavior

- **A type exists only if its file does.** The file's name is the type's name, and the file is the
  entire type: nothing is inherited, so deleting a key removes that property and deleting the file
  removes the type. Every type file sets `serves`. `info --dump-toml` shows every key a file may set.
- **`enabled = false` disables a type and keeps its file.** `init` writes `enabled` first in each
  file. `info` and the briefing list a disabled type with the line that disables it, and `check`,
  `new` and `index` refuse a note of it, naming that line.
- **Anchor fields exist only if `config.toml` declares them**, one `[anchors.<field>]` table each.
  `config.toml` holds nothing else: `types`, `extends`, `[policies]` and `exclude` are refused.
- **Unknown keys, wrong value types and contradictory properties are errors**, as are files in
  `types/` other than `<type>.toml`.
  [Type properties](type-properties.md) lists the contradictions.
- **A config that does not load stops every command** with exit 2 and a `CONFIG: <file>: <problem>`
  line on stderr. The plugin's hooks pass that line to the session, and at session start to the
  user too.
- **The profile is named `standard` while it matches the shipped one.** `doctor`'s `profile:` line
  lists the types edited, added, removed and disabled, and the anchor fields edited, added and
  removed. A newer engine's change to `standard` reaches a tree only when its files are edited to
  match.
- **No configuration suppresses a policy.** No comment in a note disables anything, and whatever
  the profile declares is enforced in full.

## Validation

- [x] **V1** -- `standard` serializes to TOML and loads back equal (`scripts/smoke.sh`).
- [x] **V2** -- the smoke test edits, adds, disables and removes a type, and fails on each of
      the errors above, naming the file.
- [ ] **V3** -- `[policies]` and `exclude` are read.

## Open questions

- Does `exclude` bind `index` and `drifted` as well as `check`?
