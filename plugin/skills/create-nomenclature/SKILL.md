---
name: create-nomenclature
description: Create a NOMENCLATURE.md in the repository's doc-marshal docs tree -- the root vocabulary, or a nested one for a subtree with words of its own. Use when the user asks to create, start or scaffold a nomenclature or vocabulary for the docs or a directory of them, or invokes /create-nomenclature.
argument-hint: "[directory] [what its subtree is about]"
---

# Create a nomenclature

Run:

```bash
doc-marshal info --vocabulary
```

and follow it, taking the "Creating" branch of each stage. `$ARGUMENTS` is the request -- the
directory the note governs and anything said about its subject.

**Ask first.** Stage 1's questions go to the user with the AskUserQuestion tool, all in one call,
as the first thing after reading the procedure -- before reading the subtree's code or notes. Offer
the likely answer as the first option. Skip any question `$ARGUMENTS` already answers. Stage 3's
confirmation is the only other time to ask.

If `doc-marshal` is not on PATH, run the project's own copy -- `uv run doc-marshal` or
`.venv/bin/doc-marshal`. If there is none, stop and tell the user, pointing at the version this
repository already pins; do not install one yourself, because which version belongs here is the
repository's decision and the latest release is rarely it. If the project has no docs tree
(`doc-marshal doctor` says so), stop and tell the user to run `doc-marshal init`.
