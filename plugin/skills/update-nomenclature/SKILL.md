---
name: update-nomenclature
description: Add, rename, redefine or retire a term in a doc-marshal NOMENCLATURE.md, and reword the notes it reaches. Use when asked to add or change a term or rule out an alias, or on /update-nomenclature.
argument-hint: "<the term change>"
---

# Update a nomenclature

Run `doc-marshal info --marshalling` and follow it with the nomenclature as the scope:
changing a term in a `NOMENCLATURE.md`. `$ARGUMENTS` is the request.

**Ask first.** Put Stage 1's questions to the user with the AskUserQuestion tool, in one call,
before reading anything else; offer the likely answer first and skip what `$ARGUMENTS` answers.

If `doc-marshal` is not on PATH, run the project's own copy -- `uv run doc-marshal` or
`.venv/bin/doc-marshal`. If there is none, stop and tell the user, pointing at the version this
repository already pins; do not install one yourself, because which version belongs here is the
repository's decision and the latest release is rarely it. If the project has no docs tree
(`doc-marshal doctor` says so), stop and tell the user to run `doc-marshal init`.
