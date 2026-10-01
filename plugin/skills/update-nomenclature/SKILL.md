---
name: update-nomenclature
description: Change the terms in a NOMENCLATURE.md of the repository's doc-marshal docs tree -- add, rename, redefine or retire a term, or rule out an alias -- and reword the notes the change reaches. Use when the user asks to add or change a term, rename a concept in the vocabulary, or invokes /update-nomenclature.
argument-hint: "<the term change>"
---

# Update a nomenclature

Run:

```bash
doc-marshal info --vocabulary
```

and follow it, taking the "Changing" branch of each stage. `$ARGUMENTS` is the request -- the term
and what should happen to it.

**Ask first.** Stage 1's questions go to the user with the AskUserQuestion tool, all in one call,
as the first thing after reading the procedure -- before grepping the tree or reading notes. Offer
the likely answer as the first option. Skip any question `$ARGUMENTS` already answers. Stage 3's
confirmation is the only other time to ask.

If `doc-marshal` is not on PATH, run the project's own copy -- `uv run doc-marshal` or
`.venv/bin/doc-marshal`. If there is none, stop and tell the user, pointing at the version this
repository already pins; do not install one yourself, because which version belongs here is the
repository's decision and the latest release is rarely it. If the project has no docs tree
(`doc-marshal doctor` says so), stop and tell the user to run `doc-marshal init`.
