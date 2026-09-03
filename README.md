# doc-marshal

A machine-checked documentation tree enforcement package.

Documentation rots because nothing connects a document to the thing that would falsify it.
`doc-marshal` makes that connection mechanical: every living note declares, in frontmatter, the
code or sources it describes -- its **anchor** -- so "which docs did this change invalidate?" is a
question with an answer a script can give.

It ships an opinionated five-type ontology, the `standard` preset. But the engine is the product:
every rule it enforces is read off a registry rather than hardcoded per check, and an ontology you
declare yourself (from 0.2) is held to exactly the same standard.

```bash
pip install doc-marshal        # or: uv tool install doc-marshal
doc-marshal init               # marks docs/ as the docs root; writes CONTEXT.md, INDEX.md, AGENTS.md
doc-marshal init --claude-code # CLAUDE.md instead, imported from the root CLAUDE.md so every session sees it
doc-marshal new reference docs/ledger/schema.md --summary "Fields of the ledger record." --code-ref src/ledger/schema.py
doc-marshal check --all        # validate every note against the ontology
doc-marshal affected           # notes whose anchors name code this branch touched
doc-marshal index              # regenerate the one generated index
doc-marshal info               # the effective ruleset, for a human or an agent
```

Zero runtime dependencies. Python 3.11 or later. Standard library only, so it also runs from a
checkout: `python3 -m doc_marshal`.

## The idea

A note is a markdown file with a small frontmatter block:

```yaml
---
type: reference
updated: 2026-08-07
summary: How the sync worker chooses between its two ingest modes.
code_refs:
  - src/ingest/sync_worker.py
  - config/ingest.yaml
---
```

`type` names one of the ontology's types. `summary` is the one line the generated index shows, so
it is the most load-bearing sentence in the doc. `code_refs` is the anchor: the paths whose change
would make this note wrong. `doc-marshal affected` reads the anchors back against a git diff and
lists the notes to look at, and CI annotates every pull request with them. That is the whole point
of writing them down.

Which anchor a type must carry follows from **authorship**. A note about a fact this repo *decides*
anchors to a repo path. A note about a fact it merely *observes* -- a datasheet value, a vendor
protocol, a measurement -- anchors to its `source`. The engine calls the repo-path fields the
**drift spine**, and only those are matched against a diff.

## The standard preset

Five types. A type names the reader it serves, and nothing else. One type per document: a change
that needs a procedure and the behaviour it implements is two notes linked to each other, not one
mixed note. Route by what the reader needs.

<!-- This table is the output of `doc-marshal info --types`; regenerate it rather than editing it. -->
| Type | Serves | Voice | Mutability | Anchor minimum |
| --- | --- | --- | --- | --- |
| `reference` | someone looking up a fact -- decided by this repo, or observed from outside it | flat, enumerative, cites its source | living -- rewritten in place as the code or the world changes | any of `code_refs`, `source` |
| `runbook` | someone running a procedure | imperative, literal, copy-pasteable | living -- rewritten in place | `code_refs` |
| `decision` | someone about to reopen a settled choice | terse, one decision | append-only -- never edited after acceptance | append-only |
| `spec` | someone reading, building or validating a feature's behaviour as a whole | declarative, whole-feature, links to the references that justify it | living at every status -- in-progress whenever the doc leads the code | `code_refs` once `done` |
| `context` | someone choosing what to call a thing | flat, definitional, opinionated | living -- rewritten as the domain sharpens | none |

The anchor minimum is *any of* the fields listed: a `reference` about a fact this repo decides
carries `code_refs`, one about a fact it observes carries `source`, and one about a vendor protocol
we implement carries both. A `spec` carries `status` (`proposed`, `in-progress`, `done`) and is
anchored once it is `done`; it is living at every status, and the validator warns when a `done`
spec is edited by a change that touched none of its code. `decision` is append-only and anchored by
its own content. `context` is falsified by the words the repo uses, not by a path.

Two of them do more than hold prose:

- **`decision`** notes live in `decisions/` as `NNNN-slug.md`, are never edited after acceptance,
  and record being replaced with `supersedes` / `superseded_by`. `doc-marshal new decision <slug>`
  derives the number.
- **`context`** is the shared vocabulary: one `CONTEXT.md` at the docs root, injected into every
  session, with a fixed table of terms, definitions and the aliases each rules out. Every other
  note is scanned against the `Avoid` column. A nested `CONTEXT.md` adds terms for its subtree and
  may never redefine an ancestor's. The vocabulary is deliberately small -- thirty-five terms, six
  thousand characters -- because every session pays for it.

The full argument for each type is `doc-marshal info <type>`; the rules that are not per-type --
naming, links, indexes, attachments, prose -- are `doc-marshal info --conventions`. They ship
inside the package and are never copied into your repository, so they cannot drift from the
version that enforces them.

## Reading the conventions without the CLI

A reviewer on a pull request cannot run `doc-marshal info`, so this repository keeps one rendering
of the standard preset, generated from the same source at the same version and committed back by
CI whenever main moves:

- [rendered/conventions.md](rendered/conventions.md) -- every rule that is not per-type
- [rendered/doc-types.md](rendered/doc-types.md) -- the five types, in full
- [rendered/process.md](rendered/process.md) -- the update-docs process, staged

They are derived, never edited: the prose lives in `src/doc_marshal/prose/`.

## What is enforced

Every rule is either an error or a warning, and there is no severity configuration, no warn-only
mode, and **no inline suppression** -- that is the one absolute prohibition. A hundred scattered
suppressions are unauditable; everything configurable lives in one file that review can see.

Errors: frontmatter parses and carries `type`, `updated` and `summary`; `type` names a live type;
required anchors are present and every anchor entry resolves by its kind; a type's placement holds
(folder, numbering, fixed filename); `status` is one the type allows; links resolve, including
heading anchors; no wikilinks, no absolute links; a `context` note's exact shape and caps; no
`README.md` in the tree.

Warnings: an `updated` date not bumped on a note the change edited, a `done` spec edited while none
of its code was, a literal em dash, a word the vocabulary rules out, and a misplaced attachment.

Minor releases may add checks. Pin the version at every enforcement point and bump when you choose.

## Where it runs

| When | What runs | Effect |
| --- | --- | --- |
| every write to a note | `doc-marshal check <that file>`, via the Claude Code plugin | reports into the session; never blocks |
| every `git commit` | `check` on staged notes, then `index`, via pre-commit | errors block; a regenerated index fails the hook for re-adding |
| every pull request | `check --all --format github`, `index --check` | errors fail the build, each on the file it names; a stale index warns |
| every pull request | `affected --format github` | annotates anchored notes; never fails |

Pre-commit, in `.pre-commit-config.yaml`:

```yaml
- repo: https://github.com/rootdrew27/doc-marshal
  rev: v0.2.0
  hooks:
    - id: doc-marshal-check
    - id: doc-marshal-index
```

CI, on every pull request. No `paths:` filter: anchors break in the change that renames or deletes
the code, which by definition touches no documentation.

```yaml
- uses: actions/checkout@v4
  with: { fetch-depth: 0 }
- run: uvx doc-marshal==0.2.* check --all --format github --range "${{ github.event.pull_request.base.sha }}..HEAD"
- run: uvx doc-marshal==0.2.* index --check
  continue-on-error: true
- run: uvx doc-marshal==0.2.* affected --range "${{ github.event.pull_request.base.sha }}..HEAD" --format github
```

### The Claude Code plugin

The `plugin/` directory is a Claude Code plugin. Its value is two hooks no other harness provides:
**PostToolUse** validation of each note the moment it is written, and **SessionStart** injection of
the index preview (folder names and counts, nothing more), the root `CONTEXT.md` verbatim, and the
enabled types. It also carries a thin `update-docs` skill that defers to `doc-marshal info --process`.

The plugin is an add-on to the package, not a second way to install it. Its hooks run the
`doc-marshal` the project already has -- the project's virtualenv first, then PATH -- so the agent
validates against the same version CI and pre-commit run. With no engine installed the hooks do
nothing, except that the session-start hook says so once in a project that has a docs root.
`doc-marshal doctor` reports what each route resolves and flags a mismatch.

`doc-marshal init --claude-code` writes `CLAUDE.md` instead of `AGENTS.md`, imports it from the
repository's root `CLAUDE.md` with one `@docs/CLAUDE.md` line so every session sees it, and allows
`doc-marshal`, `uv run doc-marshal` and `.venv/bin/doc-marshal` in `.claude/settings.json`.
`doc-marshal doctor` reports a docs-root `CLAUDE.md` the root does not import. Either file says
what the tree, its commands and its two special files are for, so a Codex or Cursor user gets the
same process by the same route with no plugin at all.

## The docs root is marked, not guessed

`doc-marshal init [path]` writes an empty `.doc-marshal.toml` into the directory (default `docs/`).
That marker is how every command finds the docs root -- never by name. A repository can hold a
Sphinx `docs/` and a marshal tree elsewhere without ambiguity, and `init` warns when the target
looks like a published site. Two markers in one repository is an error.

From 0.2 the marker holds the configuration: `extends = "standard"`, per-type overrides,
`enabled = false`, `[rules]`, `exclude`. `doc-marshal info --dump-toml` shows the schema today.

## Design

[SPEC.md](https://github.com/rootdrew27/doc-marshal/blob/main/SPEC.md) records the design and every decision behind it, including the ones that
reverse the prototype this was extracted from. When the code and that file disagree, the code is
right.

## License

MIT.
