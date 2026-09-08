---
type: reference
updated: 2026-09-07
summary: One line per module of the package, per plugin file and per script: what each one owns
code_refs:
  - src/doc_marshal
  - plugin
  - scripts
---

# Package layout

What each file owns, read from its own docstring. The verbs are one module each, imported lazily
by `cli.py`, so no verb pays for another's imports.

## `src/doc_marshal/`

| Module | Owns |
| --- | --- |
| `__init__.py` | the package docstring and `__version__`, the one source of the version |
| `__main__.py` | `python -m doc_marshal`, so the package runs from a bare checkout |
| `cli.py` | verb dispatch, the usage text and the exit status |
| `errors.py` | `DocMarshalError`, the one exception the CLI turns into a message and exit 2 |
| `settings.py` | the constants not yet configurable, behind one `Settings` object |
| `ontology.py` | `AnchorField`, `Structure`, `Supersession`, `DocType`, `Profile`, the `standard` profile, and the TOML serializer |
| `config.py` | the effective profile a docs tree is validated against; the loader lands here |
| `discovery.py` | locating the docs tree, and the repository root paths resolve against |
| `paths.py` | classifying a path under the docs tree, the note set, and exact-spelling existence |
| `frontmatter.py` | the frontmatter subset, parsed strictly; `read_note` |
| `markdown.py` | fences, headings, comments, code spans, `##` sections and table rows |
| `note.py` | one note read once: frontmatter, live type, and three views of the body |
| `git.py` | `Git`, the port every git question goes through |
| `manager.py` | `Manager`, the port `upgrade` puts the install question to |
| `integrate.py` | the integration files, and the version each one names |
| `anchors.py` | whether an anchor entry resolves by its field's `resolves` values |
| `vocabulary.py` | the terms in force for a note, and the alias patterns |
| `policies.py` | every policy as one pipeline: `NOTE_POLICIES`, `TREE_POLICIES`, `PLACEMENT_POLICIES` |
| `report.py` | how a run's errors and warnings are collected and printed, including the line prefixes the plugin's hook selects on |
| `check.py` `index.py` `drifted.py` `new.py` `info.py` `init.py` `doctor.py` `upgrade.py` `briefing.py` | one verb each |
| `doctrine/` | `doc-types.md`, `policies.md`, `marshalling.md` -- the text `info` prints |

## `plugin/`

| File | Owns |
| --- | --- |
| `.claude-plugin/plugin.json` | the plugin's name, description and version, held in step by `scripts/sync_version.py` |
| `hooks/hooks.json` | registering the two hooks and their timeouts |
| `hooks/_engine.py` | resolving the project's engine, running it, and the `MISSING_ENGINE` text |
| `hooks/session-start.py` | the [briefing](briefing.md), as `additionalContext` |
| `hooks/post-tool-use.py` | `check --skip-non-notes` on each note as it is written; never blocks |
| `skills/marshal-the-docs/SKILL.md` | a thin skill that defers to `doc-marshal info --marshalling` |

## `scripts/`

| Script | Owns |
| --- | --- |
| `render_doctrine.py` | writing `rendered/` from the doctrine and the profile; `--check` reports a stale copy |
| `sync_version.py` | every hand-copied version and the README's generated snippets; `--check`, `--set X.Y.Z` |
| `smoke.sh` | the end-to-end run on a fresh repository, including both plugin hooks with `PATH` stripped |

## What is not here

There is no `tests/` directory. CI runs `scripts/smoke.sh` on each supported Python, and checks
that `rendered/` still matches the doctrine and the profile. A suite over synthetic trees is still
the plan, and the round-trip test between the profile and its TOML form is the first case it should
hold.
