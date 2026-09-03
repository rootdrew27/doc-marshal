---
name: update-docs
description: Update the repository's doc-marshal documentation tree, agent-memory files, and in-code docs to reflect a finalized code change. Use after work is complete -- when the user says "update the docs", "document this", "sync the docs", or invokes /update-docs. Requires a docs root marked with .doc-marshal.toml. Maintains a typed doc ontology (by default reference, runbook, spec, decision, nomenclature) and verifies its own output with doc-marshal.
argument-hint: "[--auto] <what changed>"
---

# Update docs

Reflect a **finalized** code change in documentation. Run after the work is done, not during it.

The process is versioned with the engine that enforces it, so it is not restated here. Run:

```bash
doc-marshal info --process
```

and follow it, stage by stage. `$ARGUMENTS` is the change description; `--auto` at its start
selects auto mode as the process defines it (the plan gate is skipped, nothing else is).

If `doc-marshal` is not on PATH, run the project's own copy -- `uv run doc-marshal` or
`.venv/bin/doc-marshal`; if there is none, stop and tell the user to install it
(`pip install doc-marshal`). If the project has no
docs root (`doc-marshal doctor` says), stop and tell the user to run `doc-marshal init`.
