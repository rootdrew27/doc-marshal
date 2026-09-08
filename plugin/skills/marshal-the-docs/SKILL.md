---
name: marshal-the-docs
description: Write to the repository's doc-marshal docs tree, the directory marked with .doc-marshal.toml. Only for that tree -- not for docstrings, READMEs, comments or any documentation outside it, and not for installing, upgrading or configuring doc-marshal. Use whenever a request updates notes in the tree for a change, writes new ones from scratch, removes or renames stale ones, or brings the tree back in step with the code, at any point in the work -- when the user says "update the docs", "document this", "sync the docs", "write a runbook/reference/decision", "prune the docs", or invokes /marshal-the-docs. Follows the marshalling the engine prints and verifies its own output with it.
argument-hint: "[--auto] <what to do>"
---

# Marshal the docs

Write to the docs tree by the marshalling the engine ships. The marshalling is versioned with the
engine that enforces it, so it is not restated here. Run:

```bash
doc-marshal info --marshalling
```

and follow it, stage by stage. `$ARGUMENTS` is the request -- a change to reflect, a subject to
write up, notes to remove, or anything else that writes to the tree; `--auto` at its start selects
auto mode as the marshalling defines it (the plan gate is skipped, nothing else changes).

If `doc-marshal` is not on PATH, run the project's own copy -- `uv run doc-marshal` or
`.venv/bin/doc-marshal`. If there is none, stop and tell the user, pointing at the version this
repository already pins; do not install one yourself, because which version belongs here is the
repository's decision and the latest release is rarely it. If the project has no docs tree
(`doc-marshal doctor` says so), stop and tell the user to run `doc-marshal init`.
