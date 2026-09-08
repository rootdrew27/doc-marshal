---
type: reference
updated: 2026-09-07
summary: Every property a type declares, what the validator enforces from it, and what the scaffolder writes from it
code_refs:
  - src/doc_marshal/ontology.py
---

# What a type declares

A type is data. `DocType` in `src/doc_marshal/ontology.py` is the single internal representation:
the validator enforces from it, `doc-marshal new` writes from it, and `doc-marshal info` renders
it. No policy hardcodes a type name. The [standard profile](standard-profile.md) constructs its
five types in Python; the configuration loader of a later release is an alternate constructor for
the same objects.

## Properties

| Property | Meaning |
| --- | --- |
| `name` | the value a note's `type:` carries |
| `serves`, `voice`, `mutability` | text only `info` renders |
| `enabled` | whether the type is live; `enabled = false` in config removes it from the effective profile |
| `requires` | anchor fields of which a note must carry at least one -- a minimum, not a permitted set |
| `requires_from` | the `status` from which `requires` binds; unset means always |
| `statuses` | the values `status:` may take; empty means the type has no status |
| `default_status` | what `new` writes when `--status` is omitted |
| `folder` | the one folder under the docs tree this type lives in |
| `numbered` | the filename carries a unique `NNNN-` prefix, and the H1 repeats the number |
| `supersession` | the field pair and status recording that this note was replaced |
| `template` | what `new` writes after the frontmatter and H1 |
| `reserved_filename` | the one filename this type may take, exempt from the naming pattern |
| `root_required` | one instance must exist at the top of the docs tree |
| `additive` | a nested instance may not redefine a key an ancestor defines |
| `append_only` | never edited after acceptance, so its wording cannot be corrected |
| `structure` | the parsed body shape, for a type whose body is data |
| `required_sections` | the `##` sections a free-form note carries |
| `empty_at` | `(section, status)` pairs: in that status the section, if present, is blank |
| `description` | the longer argument for a user-declared type; the profile's own lives in `doctrine/` |

`Supersession` names three values: `forward` (`supersedes`), `back` (`superseded_by`) and the
`status` that requires the back-pointer.

## The keys a note of that type may carry

`Profile.frontmatter_keys` builds the permitted set from the profile, so it is the same list the
validator rejects an unknown key by and `info` prints:

- `type`, `updated` and `summary`, on every note of every type;
- every anchor field the profile declares -- legal on every type, whether or not that type requires
  it, and validated whenever present;
- `status`, only where the type has statuses;
- the supersession pair, only where the type declares one.

Any other key is an error. What each value must *be* -- the date form, the summary cap, how an
anchor entry resolves -- is `doc-marshal info --policies` and [anchors](anchors.md).

## `required_sections` and `empty_at`

A free-form type's required sections are each present once, in the declared relative order, and
each written -- content is measured after HTML comments are stripped. Other sections may appear
anywhere. `empty_at` is the reverse: in the named status the section may exist only if it is
blank, which is how a `done` spec is held to having no open questions.

The profile refuses a type whose `template` does not write its required sections in that order, so
`new` and `check` read one list and a scaffold can never be missing a section the validator will
demand.

## `structure`

`structure` exists for a type whose body is data other checks parse rather than free-form text. It
declares the exact `##` sections in order, the section holding the table, the table's columns, the
key column, the column the cell cap bounds, the columns other notes are scanned against, and three
caps: rows, cell length, and characters outside the table's rows.

Every shape departure is an **error**, not a warning. A renamed column does not degrade the checks
built on it -- it silently turns them off, and a check that has quietly stopped running is worse
than one that never existed. `nomenclature` is the only type in the standard profile with a
`structure`, and its `Avoid` column is what every other note is scanned against.

## Combinations the profile refuses

`Profile` validates its own types on construction, so a property that would quietly never bind is
a startup error rather than a silent no-op:

- `requires` naming an undeclared anchor field; `default_status` or `requires_from` naming a status
  the type lacks; `supersession.status` outside `statuses`; `default_status` set to the replaced
  status.
- `structure` naming columns it lacks, or a `table_in` outside its own sections.
- `numbered` without a `folder`, `root_required` without a `reserved_filename`, `additive` without
  a `structure`.
- `structure` together with `required_sections` -- two answers to one question.
- `required_sections` repeating a section, or naming one the `template` does not write in that
  order; `empty_at` naming a section twice, or one that is also required.
