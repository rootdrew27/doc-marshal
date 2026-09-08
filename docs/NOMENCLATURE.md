---
type: nomenclature
updated: 2026-09-07
summary: The project's shared terminology -- one word per concept, the aliases ruled out, and the live ambiguities. Emitted into every session.
---

# doc-marshal shared vocabulary

The words doc-marshal's code, SPEC and notes use for the parts of the product, in the register of
the name: a marshal enforces the law. One word per concept; the alternatives in `Avoid` are ruled
out, not merely discouraged.

## Terminology

| Term | Definition | Avoid |
| --- | --- | --- |
| engine | The `doc-marshal` package and CLI: the validator, index builder and drift detector that reads every policy off an effective profile rather than hardcoding it. | linter, checker |
| note | One typed markdown file under the docs tree, with frontmatter the effective profile validates and a body its type shapes. | page, article, document |
| type | What a note is, named for the reader it serves and nothing else; declared as data whose properties the validator enforces and the scaffolder applies. | kind, category |
| property | One declared line of a type: `serves`, `requires`, `folder`, `template` and the rest, each enforced by the validator and applied by the scaffolder. | attribute, declaration |
| profile | A shipped ontology. `standard` is the five-type one: reference, runbook, decision, spec, nomenclature. | preset, default ontology |
| ontology | A set of types and anchor fields, with the argument for why each type exists. | taxonomy |
| effective profile | The profile a docs tree is validated against once its config's changes apply; today, always `standard` unchanged. | registry |
| anchor | A frontmatter field naming what outside a note would falsify it; each field declares how its entries resolve. | link, dependency |
| drift | Anchored code changing while the note anchored to it does not. | rot, bit-rot |
| drifted | The notes whose path-valued anchors name something a change touched: a prompt to look, not a verdict. | affected, impacted |
| docs tree | The one directory the engine governs and everything under it: the directory holding the config, found by the config and never by name. | docs root, docs folder, docs dir, documentation directory |
| config | `.doc-marshal.toml`, which marks the docs tree by existing and will carry the profile's adjustments. | marker, manifest |
| mutable | A note rewritten in place as its subject changes. | living, evergreen |
| append-only | A note never edited after acceptance, so its wording cannot be corrected; anchored by its own content. | immutable, frozen |
| supersession | A later note replacing an append-only one, recorded by a field and a status on the replaced note. | deprecation, retirement |
| template | What `new` writes for a type after the frontmatter and H1. | skeleton, boilerplate, stub |
| structure | The parsed body shape a data-bodied type declares: sections, columns, key column, scanned columns and caps. | schema |
| policy | One check the engine enforces, read off the effective profile; a type's properties are data the policies read, not policies. | rule, lint |
| report | The errors and warnings a run collected. Errors exit 1; warnings never fail a run. | diagnostics, findings |
| index | `INDEX.md`: the generated routing surface, one line per note with its type and summary, never written by hand. | table of contents, TOC, sitemap, catalog |
| asset | A file under `assets/`, exempt from validation and named as a note's `source`. | attachment, media |
| reserved filename | The one filename a type binds both ways: that type must use it, and no other type may. | fixed name, claimed name |
| integration | A place `check` runs: the plugin's PostToolUse hook, the pre-commit framework, and CI. | enforcement point, gate |
| jurisdiction | One of the four places that name an engine version and must all name the same one: the environment, `pyproject.toml`, the pre-commit `rev:`, and the CI pin. | facet, version facet |
| pin | A jurisdiction's exact version: `==X.Y.Z` or `rev: vX.Y.Z`. | constraint, version spec |
| briefing | The three blocks SessionStart hands a fresh session: the index preview, the root vocabulary as content, and the compact info block. | session injection, context dump, preamble |
| doctrine | The text shipped inside the package and printed by `info`: the types, the policies and the marshalling. `rendered/` holds generated copies. | prose, help text |
| marshalling | The staged procedure for writing to the docs tree, for a change, a subject, or a clean-up. | process, playbook, docs run |

## Relationships

- An effective profile is one profile as adjusted by one config; today no config adjusts anything, so it is always `standard`.
- A type declares anchor minimums; `drifted` reads every path-valued anchor against a change.
- A policy runs over a note and writes into the report; an integration is where the policies run.
- Every jurisdiction that names a version names the same one; a pin is a jurisdiction's value; `doctor` reads them and `upgrade` moves them together.
- The briefing is performed by the plugin's SessionStart hook and reads the index, the root vocabulary and the effective profile.

## Ambiguities

- `hook` is a plugin hook, a pre-commit hook, and the entry `.pre-commit-hooks.yaml` declares. The frameworks own the word.
