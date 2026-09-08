---
type: spec
updated: 2026-09-07
summary: What doc-marshal is: an engine that reads every policy off an effective profile, ships its doctrine in the package, and holds one version everywhere
status: done
code_refs:
  - src/doc_marshal
  - scripts/render_doctrine.py
---

# The doc-marshal engine

## Overview

doc-marshal is a documentation system for repositories whose primary reader is a coding agent. It
has three parts: an engine -- a validator, an index builder and a drift detector over a tree of
typed markdown notes; the `standard` [profile](standard-profile.md), a five-type ontology shipped
as data; and [integrations](integrations.md) that run the engine at every write, every commit and
every pull request. The engine is the product, and the shipped ontology is one profile among the
ones a later release lets a repository declare. It starts at the directory holding
`.doc-marshal.toml` and stops there: nothing outside that tree is validated, indexed or briefed.

The distinguishing idea is the [anchor](anchors.md): every note declares in frontmatter what
outside itself would falsify it, so "which notes did this change invalidate?" has a mechanical
answer.

## Behavior

- Every policy is read off the effective profile rather than branched on by type name, so a new
  type is a profile entry and no check changes (`NOTE_POLICIES` in `src/doc_marshal/policies.py`).
- The effective profile is one profile as adjusted by one config. Today `config.py` returns
  `STANDARD` unchanged, and a config carrying any key exits 2 -- see
  [configuration](configuration.md) for the loader that replaces it.
- A type is data: [what it declares](type-properties.md) is enforced by the validator and applied
  by the scaffolder, from one `DocType` the profile constructs in Python.
- The docs tree is located by `--docs-tree`, then `DOC_MARSHAL_DOCS_TREE`, then the config file,
  and never by directory name (`discovery.py`). One repository has one docs tree.
- Anchor fields are declared, not fixed. Which of them a change is matched against follows from
  their `resolves` values, and `doc-marshal drifted` is what reads them back.
- The verbs, their flags and their exit statuses are the [CLI surface](cli.md); a fresh session is
  handed the [briefing](briefing.md).
- The doctrine -- the policies, the argument for each type, the marshalling -- ships inside the
  package as `src/doc_marshal/doctrine/` and is obtained by running `doc-marshal info`. It is
  never copied into a user's repository, so no copy can go stale and output is filtered to the
  enabled types.
- `rendered/` is derived, for a reviewer on a pull request who cannot run the CLI.
  `scripts/render_doctrine.py` writes it from the same source `info` renders; the pre-commit hook
  regenerates it and `.github/workflows/render.yml` commits it back on every push to main.
- Releases follow SemVer, and a minor release may add policies. Pinning is what makes that safe,
  and every pin is one of the four [jurisdictions](jurisdictions.md) that must name one version.
- Whatever the effective profile results in is enforced completely: no inline suppression, no
  severity configuration, no warn-only mode. [Configuration](configuration.md) says what no
  configuration reaches.
- The constants a later release exposes -- the filename pattern, the summary cap, the index and
  asset directory names, the forbidden names, the excluded directories -- are routed through one
  `Settings` object today, so exposing them is an addition rather than a refactor through six
  modules.
- There is no test suite yet. CI runs `scripts/smoke.sh` end to end on each supported Python; the
  [package layout](modules.md) says what else runs.

## Validation

- [x] **V1** -- `check --all` reproduces the prototype's output on the prototype's own tree, note
      for note, with the config placed in its existing `agent-docs/` directory.
- [x] **V1b** -- `init` warns on a `docs/` holding `conf.py` or `mkdocs.yml` and says what it
      found; every command fails legibly when no config exists.
- [x] **V1c** -- a repository holding both a Sphinx `docs/` and a marked tree validates only the
      marked one.
- [ ] **V2** -- the round-trip test passes: the `standard` profile serializes to TOML, loads back,
      and compares equal.
- [x] **V3** -- the plugin's hooks validate a note through the engine in the project's virtualenv;
      with no engine installed, SessionStart says so once and PostToolUse stays silent.
- [x] **V4** -- `doctor` reports a deliberate version mismatch between a repository pin and the
      installed engine.
- [x] **V5** -- a real project runs a full marshalling cycle against the extracted tool, with the
      thin skill, and the agent completes it without the doctrine it used to carry.
- [x] **V6** -- a fresh session's briefing is under 1000 characters on a 300-note tree.
- [x] **V7** -- `pre-commit run --all-files` blocks a commit carrying an invalid note, and the
      index regeneration fails for re-adding rather than silently staging.
