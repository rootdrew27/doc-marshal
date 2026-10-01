---
name: update-nomenclature
description: Add, rename, redefine or retire a term in a doc-marshal NOMENCLATURE.md, and reword the notes it reaches. Use when asked to add or change a term or rule out an alias, or on /update-nomenclature.
argument-hint: "<the term change>"
---

# Update a nomenclature

**Ask first.** Before running anything, make one AskUserQuestion call with one multi-select
question, what to do to the nomenclature, offering "Add Term(s)", "Modify Term(s)" and
"Remove Term(s)". Then ask what the chosen actions need: the terms, and for a rename, which word
wins and whether the other goes under `Avoid`. Skip the AskUserQuestion call only when
`$ARGUMENTS` already says which terms to add, modify or remove, and how.

Then run `doc-marshal info --marshalling` and follow it with the nomenclature as the scope:
changing terms in a `NOMENCLATURE.md`. `$ARGUMENTS` is the request; the answers above are
Stage 1's.

If `doc-marshal` is not on PATH, run the project's own copy -- `uv run doc-marshal` or
`.venv/bin/doc-marshal`. If there is none, stop and tell the user, pointing at the version this
repository already pins; do not install one yourself, because which version belongs here is the
repository's decision and the latest release is rarely it. If the project has no docs tree
(`doc-marshal doctor` says so), stop and tell the user to run `doc-marshal init`.
