---
type: spec
updated: 2026-09-08
summary: "Configuration as designed and unbuilt: the config file, extends, per-type merge, disabling a type, the policies table and exclude"
status: proposed
code_refs:
  - src/doc_marshal/config.py
---

# Configuration

## Overview

A docs tree adjusts the profile it is validated against by writing keys into its own
`.doc-marshal.toml`. This note is the design of that loader. **None of it is built.** Today
`load_profile` in `src/doc_marshal/config.py` returns the `standard` profile unchanged, and a
config carrying any key at all is refused with exit 2 and a message saying that configuration
arrives in a later release -- a configuration that validated as nothing would be exactly the silent failure this
tool exists to remove.

The file itself already exists and is not renamed when the loader lands: `init` writes it with a
comment and no keys, and it marks the docs tree by existing. An empty file is valid TOML, so
nothing about its present form has to change.

## Behavior

The config is read with `tomllib`, standard library from Python 3.11, which is the floor this
package sets.

**Composition.** `extends` names the profile to start from.

```toml
extends = "standard"   # the default when omitted; `extends = []` starts from nothing
```

Profiles are named and shipped inside the package, so adding one is more data behind the same key.
Merge-by-default is refused because it makes the shipped types unremovable furniture;
replace-by-default is refused because adding one type would mean retyping every template.

**Merge is per type, shallow, over the extended profile.** `[types.reference] serves = "..."`
yields the shipped `reference` with one property replaced, not a fresh type whose other properties
revert to defaults -- otherwise adding a `folder` to `decision` would silently strip its numbering,
supersession and template. Nested tables merge the same way, so
`[types.nomenclature.structure] max_rows = 30` overrides one number without restating the columns,
the sections or the other caps.

**Disabling is a value in the type's own table**, not a parallel list:

```toml
[types.runbook]
enabled = false
```

This is the eslint, stylelint and pyright shape rather than ruff's select-and-ignore lists, which
exist because ruff has thousands of prefix-namespaced codes. Types are a small named space, so a
typo'd `[types.histry]` is a reportable unknown-type error where a `disable = ["histry"]` entry
would be silently a no-op, and disabling needs no mechanism beyond the merge that already exists.

**Weakening a shipped type is permitted.** A type's table spells its anchor minimum as one
boolean per declared anchor field, beside the properties -- `requires` and `requires_from` are how
`DocType` holds it, not what the file writes -- so `[types.reference] code_refs = false` is legal
and drops that field from the minimum. "Always
enforced" is a property of the engine, not of the shipped profile: whatever effective profile
results is enforced completely, with no severity configuration and no warn-only mode.

**A `[policies]` table configures what is not per-type**, expressed as values, with disabling as a
legal value -- an empty `forbidden_names` turns that policy off. Same shape as `enabled`, so there
is one idea to learn rather than two. These are the constants routed through `Settings` today.

```toml
[policies]
filename_pattern = "^[a-z0-9-]+$"
summary_max = 300
forbidden_names = []
exclude = ["docs/legacy/**"]
```

`exclude` is the incremental-adoption mechanism: it quarantines *files* visibly rather than
weakening a policy everywhere. Partial adoption already half-works, because `check` takes a file
list and pre-commit passes only the staged notes; `exclude` extends that to `--all` in CI.

**What no configuration reaches.** There is no inline suppression: no comment in a note disables
anything, and this is the one prohibition defended absolutely. Whatever the effective profile
says, these hold regardless of it: frontmatter parses; `type` names a live type; an anchor entry
resolves by its field's `resolves` values wherever one is present; markdown references resolve,
heading anchors included; a type's declared properties hold; and the index is generated rather than written.

## Validation

This note adds no item of its own. Its one test is [the engine](engine.md)'s V2, the round-trip
of the `standard` profile through `to_toml` and `from_dict`: if the shape cannot express the
shipped profile, the shape is too weak, and that is discovered before a user's report.

## Open questions

- Does a user-declared type's longer argument stay a `description` string, or gain a
  `description_file` key? Multi-paragraph markdown inside a TOML string is miserable to author and
  to diff.
- Does `exclude` bind the index builder and `drifted` as well as `check`, or only `check`?
- Which second profile ships first, and does it need any mechanism `extends` does not already have?
