---
name: create-nomenclature
description: Create a NOMENCLATURE.md in the doc-marshal docs tree, at the root or for a subtree with words of its own. Use when asked to create or start a nomenclature or vocabulary, or on /create-nomenclature.
argument-hint: "[directory] [what its subtree is about]"
---

# Create a nomenclature

Run `doc-marshal info --marshalling` and follow it with the nomenclature as the scope:
creating a `NOMENCLATURE.md` -- the root one or a nested one. `$ARGUMENTS` is the request.

**Ask first.** Put Stage 1's questions to the user with the AskUserQuestion tool, in one call,
before reading anything else; offer the likely answer first and skip what `$ARGUMENTS` answers.

If `doc-marshal` is not on PATH, run the project's own copy -- `uv run doc-marshal` or
`.venv/bin/doc-marshal`. If there is none, stop and tell the user, pointing at the version this
repository already pins; do not install one yourself, because which version belongs here is the
repository's decision and the latest release is rarely it. If the project has no docs tree
(`doc-marshal doctor` says so), stop and tell the user to run `doc-marshal init`.
