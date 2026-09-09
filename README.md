# doc-marshal

A machine-checked documentation tree enforcement package.

Documentation drifts because nothing connects a note to the thing that would falsify it.
`doc-marshal` makes that connection mechanical: every mutable note declares, in frontmatter, the
code or sources it describes -- its **anchor** -- so "which docs did this change invalidate?" is a
question with an answer a script can give.

It ships an opinionated five-type ontology, the `standard` profile. But the engine is the product:
every policy it enforces is read off the effective profile rather than hardcoded per check, and an
ontology you declare yourself (in a later release) is held to exactly the same standard.

```bash
pip install doc-marshal        # or: uv tool install doc-marshal
doc-marshal init               # marks docs/ as the docs tree; writes NOMENCLATURE.md, INDEX.md, AGENTS.md
doc-marshal init --claude-code # CLAUDE.md instead, imported from the root CLAUDE.md; installs the plugin
doc-marshal init --pre-commit --ci  # write the commit and pull-request integrations, pinned to this version
doc-marshal new reference docs/ledger/schema.md --summary "Fields of the ledger record." --code-ref src/ledger/schema.py
doc-marshal check --all        # validate every note against the ontology
doc-marshal drifted            # notes whose anchors name code this branch touched
doc-marshal index              # regenerate the one generated index
doc-marshal info               # the effective profile, for a human or an agent
```

Zero runtime dependencies. Python 3.11 or later. Standard library only, so it also runs from a
checkout: `python3 -m doc_marshal`.

**Supported: Claude Code on macOS and Linux, inside a git repository.** That is the combination
the plugin's hooks, the root import line and the smoke test exercise. The CLI, pre-commit and CI
paths run anywhere Python does, so Windows and other agents get those and nothing tested beyond
them. Git is not optional: anchors must be tracked, and the change a run is scoped to is a diff.

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
it is the most load-bearing sentence in the note. `code_refs` is the anchor: the paths whose change
would make this note wrong. `doc-marshal drifted` reads the anchors back against a git diff and
lists the notes to look at, and CI annotates every pull request with them. That is the whole point
of writing them down.

Which anchor a type must carry follows from **authorship**. A note about a fact this repo *decides*
anchors to a repo path. A note about a fact it merely *observes* -- a datasheet value, a vendor
protocol, a measurement -- anchors to its `source`. Only the **repo-path anchor fields** are
matched against a diff.

## The standard profile

Five types. A type names the reader it serves, and nothing else. One type per note: a change
that needs a procedure and the behaviour it implements is two notes linked to each other, not one
mixed note. Route by what the reader needs.

<!-- This table is the output of `doc-marshal info --types`; regenerate it rather than editing it. -->
| Type | Serves | Voice | Mutability | Anchor minimum |
| --- | --- | --- | --- | --- |
| `reference` | someone looking up a fact -- decided by this repo, or observed from outside it | flat, enumerative, cites its source | mutable -- rewritten in place as the code or the world changes | any of `code_refs`, `source` |
| `runbook` | someone running a procedure | imperative, literal, copy-pasteable | mutable -- rewritten in place | `code_refs` |
| `decision` | someone about to reopen a settled choice | terse, one decision | append-only -- never edited after acceptance | none |
| `spec` | someone reading, building or validating a feature's behaviour as a whole | declarative, whole-feature, links to the references that justify it | mutable at every status -- in-progress whenever the doc leads the code | `code_refs` once `done` |
| `nomenclature` | someone choosing what to call a thing | flat, definitional, opinionated | mutable -- rewritten as the domain sharpens | none |

The anchor minimum is *any of* the fields listed: a `reference` about a fact this repo decides
carries `code_refs`, one about a fact it observes carries `source`, and one about a vendor protocol
we implement carries both. A `spec` carries `status` (`proposed`, `in-progress`, `done`) and is
anchored once it is `done`; it is mutable at every status, and the validator warns when a `done`
spec is edited by a change that touched none of its code. `decision` is append-only and anchored by
its own content. `nomenclature` is falsified by the words the repo uses, not by a path.

Each type has the shape its reader needs, and the validator holds a note to it. Every note has one
H1, first. A `decision` carries Context, Decision, Alternatives considered and Consequences; a
`spec` carries Overview, Behavior and Validation, and may keep Open questions until it is `done`;
a `runbook` carries Prerequisites and Steps. Required sections are present, in order, and written;
other sections go anywhere. A `reference` takes the shape of its subject. `doc-marshal new` writes
the template, and the note passes once it is written.

Two of them do more than hold text:

- **`decision`** notes live in `decisions/` as `NNNN-slug.md`, are never edited after acceptance,
  and record being replaced with `supersedes` / `superseded_by`. `doc-marshal new decision <slug>`
  derives the number.
- **`nomenclature`** is the shared vocabulary: one `NOMENCLATURE.md` at the docs tree, in every
  session's briefing, with a fixed table of terms, definitions and the aliases each rules out. Every other
  note is scanned against the `Avoid` column. A nested `NOMENCLATURE.md` adds terms for its subtree and
  may never redefine an ancestor's. The vocabulary is deliberately small -- thirty-five terms, and
  three thousand characters of text around them -- because every session pays for it.

The full argument for each type is `doc-marshal info <type>`; the policies that are not per-type --
naming, frontmatter, links, the index, assets, structure -- are `doc-marshal info --policies`.
Every policy there is one `check` enforces. They ship inside the package and are never copied into
your repository, so they cannot drift from the version that enforces them.

## Reading the policies without the CLI

A reviewer on a pull request cannot run `doc-marshal info`, so this repository keeps one rendering
of the standard profile, generated from the same source at the same version and committed back by
CI whenever main moves:

- [rendered/policies.md](rendered/policies.md) -- every policy that is not per-type
- [rendered/doc-types.md](rendered/doc-types.md) -- the five types, in full
- [rendered/marshalling.md](rendered/marshalling.md) -- marshalling, staged

They are derived, never edited: the doctrine lives in `src/doc_marshal/doctrine/`.

## What is enforced

Every policy is either an error or a warning, and there is no severity configuration, no warn-only
mode, and **no inline suppression** -- that is the one absolute prohibition. A hundred scattered
suppressions are unauditable; everything configurable lives in one file that review can see.

Errors: frontmatter parses and carries `type`, `updated` and `summary` and no key the type does
not declare; `type` names a live type; required anchors are present and every anchor entry
resolves by its kind, spelled exactly with no dot segments, to something strictly inside the
repository and tracked by git; an edited note's `updated` is no earlier than the day the change
began; one H1, first, numbered where the filename is; the type's required sections, present, in
order and written; a type's placement holds (folder, numbering, reserved filename); `status` is one
the type allows, and a note naming its replacement says so; links and images resolve, including
exact heading anchors; no wikilinks, no absolute links; a `nomenclature` note's exact shape, caps
and one row per term; no `README.md`, second index or misspelled `.md` in the tree; no misplaced
asset. Everything a script can judge on shape alone is an error.

Warnings, the two policies that judge meaning: a `done` spec edited while none of its code was, and
a word the vocabulary rules out.

Minor releases may add checks. Pin the version in every jurisdiction and bump when you choose.

## Where it runs

| When | What runs | Effect |
| --- | --- | --- |
| every write to a note | `doc-marshal check <that file>`, via the Claude Code plugin | reports into the session; never blocks |
| every `git commit` | `check` on staged notes, then `index`, via pre-commit | errors block; a regenerated index fails the hook for re-adding |
| every pull request | `check --all --format github`, `index --check` | errors fail the build, each on the file it names; a stale index warns |
| every pull request | `drifted --format github` | annotates anchored notes; never fails |

`doc-marshal init --pre-commit --ci` writes both, at the version of the engine that writes them.
The snippets below are the same files for a repository that already has one; `--pre-commit` prints
this block rather than editing a config that exists, and `--ci` skips a repository with no
`.github/`.

Pre-commit, in `.pre-commit-config.yaml`:

<!-- generated: pre-commit -->
```yaml
- repo: https://github.com/rootdrew27/doc-marshal
  rev: v0.4.0
  hooks:
    - id: doc-marshal-check
    - id: doc-marshal-index
```

CI, on every pull request. No `paths:` filter: anchors break in the change that renames or deletes
the code, which by definition touches no documentation. `fetch-depth: 0` because `drifted` and
`--range` answer from a git diff, and a shallow clone makes them answer *nothing* rather than fail.

<!-- generated: ci -->
```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0
- uses: astral-sh/setup-uv@v6
- run: uvx doc-marshal==0.4.* check --all --format github --range "${{ github.event.pull_request.base.sha }}..HEAD"
- run: uvx doc-marshal==0.4.* index --check
  continue-on-error: true
- run: uvx doc-marshal==0.4.* drifted --range "${{ github.event.pull_request.base.sha }}..HEAD" --format github
```

### The Claude Code plugin

The `plugin/` directory is a Claude Code plugin. Its value is two hooks no other harness provides:
**PostToolUse** validation of each note the moment it is written, and **SessionStart** briefing with
the index preview (folder names and counts, nothing more), the root `NOMENCLATURE.md` as one line per
term plus its text sections, and the enabled types. It also carries a thin `marshal-the-docs` skill for any write to the tree -- update, write from scratch, remove -- that defers to `doc-marshal info --marshalling`.

The plugin is an add-on to the package, not a second way to install it. Its hooks run the
`doc-marshal` the project already has -- the project's virtualenv first, then PATH -- so the agent
validates against the same version CI and pre-commit run. With no engine installed the hooks do
nothing, except that the session-start hook says so once in a project that has a docs tree.
`doc-marshal doctor` reports what each route resolves and flags a mismatch.

`doc-marshal init --claude-code` writes `CLAUDE.md` instead of `AGENTS.md`, imports it from the
repository's root `CLAUDE.md` with one `@docs/CLAUDE.md` line so every session sees it, allows
`doc-marshal`, `uv run doc-marshal` and `.venv/bin/doc-marshal` in `.claude/settings.json`, and
installs the plugin itself -- `claude plugin marketplace add` and `claude plugin install --scope
project`, both idempotent. Project scope means the enablement lands in the repository's own
`.claude/settings.json`, so the hooks arrive with a clone instead of with whoever remembers to run
`/plugin`. No `claude` on PATH, or `--no-plugin`, prints the two commands instead.
`doc-marshal doctor` reports a docs-tree `CLAUDE.md` the root does not import. Either file says
what the tree, its commands and its two special files are for, so a Codex or Cursor user gets the
same marshalling by the same route with no plugin at all.

## Installing, and one version everywhere

### With `uv`

Four commands, from the repository root:

```bash
uv add --dev doc-marshal==0.4.0                          # into the project's .venv, where the plugin's hooks look
uv run doc-marshal init --claude-code --pre-commit --ci  # the config, the pointer file, and both integrations
uv run doc-marshal check --all                           # the tree validates from its first minute
uv run doc-marshal doctor                                # every route to the engine resolves the same version
```

Drop `--claude-code` for the vendor-neutral `AGENTS.md`. Drop `--pre-commit` or `--ci` and `init`
names the flag that writes it rather than printing a config block to paste. A repository that is not a Python
project has no dependency table to add to, so put the engine on PATH instead:
`uv tool install doc-marshal==0.4.0`.

Upgrading is one command, and it moves every version this repository names at once:

```bash
uv run doc-marshal upgrade 0.4.0   # install it, move every pin, then doctor and check --all
```

### Other project managers

Supported, set up by hand. Everything after the install is identical -- `init`, `check`, `doctor`,
the pre-commit hook and the CI workflow do not care which manager put the engine there -- and
`upgrade` detects your manager and prints the two commands to run rather than running them.

**The one thing to get right is where the engine lands.** The plugin's hooks run the project's own
`.venv/` or `venv/` first, then PATH. An engine installed anywhere else leaves them running
nothing, which reads exactly like a clean tree -- the failure mode that looks most like success.

| The project uses | Install with | Hooks find it |
| --- | --- | --- |
| pip with a virtualenv in the tree | `pip install doc-marshal==0.4.0` | yes, `.venv/` or `venv/` |
| Poetry with `virtualenvs.in-project true` | `poetry add --group dev doc-marshal==0.4.0` | yes, `.venv/` |
| Poetry with the default environment | -- | **no**: the environment sits outside the repository under a hashed name. Turn on in-project virtualenvs and reinstall, or install to PATH. |
| nothing in particular | `uv tool install doc-marshal==0.4.0` | yes, PATH |

Then `doc-marshal init --claude-code --pre-commit --ci`, `check --all` and `doctor`, as above.

### One version, everywhere

**Every jurisdiction that names a version names the same one; a jurisdiction may be absent.** There
are four: the project's environment, `pyproject.toml`, the pre-commit `rev:`, and the CI pin. Having
no pre-commit config or no CI is fine, and `doctor` says so without complaint. Two of them naming
different versions is not: an agent would validate against one version and CI against another.

`doc-marshal doctor` reports every route to the engine and exits 1 when any two disagree. Run it
after any install, and after anything that moves a version on its own -- `pre-commit autoupdate` in
particular, which moves the `rev:` and leaves the other three jurisdictions behind. `doc-marshal
upgrade` exists so that never happens: it drives the install and then re-runs itself as the version
it just installed, so the repository is never left between two versions with its own `doctor`
failing.

A minor release may enforce checks the previous one did not (see [Design](#design)), so `upgrade`
runs `check --all` as part of the upgrade rather than letting it surprise you after.

## The docs tree is marked, not guessed

`doc-marshal init [path]` writes an empty `.doc-marshal.toml` into the directory (default `docs/`).
That config is how every command finds the docs tree -- never by name. A repository can hold a
Sphinx `docs/` and a marshal tree elsewhere without ambiguity, and `init` warns when the target
looks like a published site. Two configs in one repository is an error.

In a later release the config holds the profile's adjustments: `extends = "standard"`, per-type
overrides, `enabled = false`, `[policies]`, `exclude`. `doc-marshal info --dump-toml` shows the
schema today. Until then it holds no keys: `init` writes it with a comment saying so, and a config
carrying any key fails every command with exit 2. There is no escape hatch before the loader exists.

## Design

The design lives in this repository's own docs tree under [docs/](docs/), starting from
[docs/INDEX.md](docs/INDEX.md). When the code and a note disagree, the code is right.

## License

MIT.
