---
type: reference
updated: 2026-09-08
summary: The standard profile's five types: why two carry no anchor, the lifecycle they share, and why there is no Related section
code_refs:
  - src/doc_marshal/ontology.py
---

# The standard profile

`standard` is the profile shipped in `src/doc_marshal/ontology.py` and the one every docs tree is
validated against today. It declares five types and two [anchor fields](anchors.md). A type names
the reader it serves and nothing else; its anchor minimum follows from what outside the note would
falsify it.

## The types

The types are `reference`, `runbook`, `decision`, `spec` and `nomenclature`, in that order: it is
the order `info` lists them in, most common first. The engine renders the rest from the profile,
so this note does not restate it: `doc-marshal info` gives each type's reader, voice, mutability
and anchor minimum in a table, and `doc-marshal info <type>` gives one type's argument with the
[properties](type-properties.md) it sets -- required sections, placement, lifecycle. The same
rendering is committed for readers without the CLI as `rendered/doc-types.md`.

Two types require no anchor. A `decision` is append-only and anchored by its own content; a
`nomenclature` note is falsified by the words the repository uses, not by a path, and anchoring it
to code would report it on every unrelated change.

## The shared lifecycle

`LIFECYCLE` is `proposed`, `in-progress`, `done`, a profile constant a type opts into by naming it
as its `statuses`. `spec` is the only type that does. A type with its own vocabulary declares that
instead: a `decision` is `accepted` or `superseded`, never "done".

`requires_from` names the status from which the anchor minimum binds. A `spec` names no code until
the code exists, so it is unanchored while `proposed` or `in-progress` and anchored once `done`.
A `done` spec edited by a change that touched none of its `code_refs` is a warning, because the
note may now lead the code and the status would no longer be true.

Anchor minimums are any-of, not permitted sets: `requires` lists the fields of which a note must
carry at least one, and any declared field is legal on any type and validated whenever present.

## Why there is no `## Related` section

An earlier convention required a trailing list of neighbouring notes at the end of every note. It
is gone. Inline markdown references on first mention already carry the connectivity, and the
validator resolves each one; the trailing list restated those same references with a reason
clause, and the reason clause was the only thing it added.
