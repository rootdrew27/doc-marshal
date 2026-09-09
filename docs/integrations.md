---
type: reference
updated: 2026-09-08
summary: Where check runs, how the Claude Code plugin wires it, what init writes for other agents, and the pre-commit and CI entries
code_refs:
  - plugin
  - .pre-commit-hooks.yaml
  - src/doc_marshal/init.py
  - src/doc_marshal/integrate.py
---

# Integrations

An integration is a place `check` runs. There are three -- the plugin's write hook, the pre-commit
framework, and CI -- and `doc-marshal init --claude-code --pre-commit --ci` wires all of them at
the version of the engine that writes them. The table of what runs where, and with what effect, is
the last section of `doc-marshal info --policies`, which ships with the engine; this note carries
what the doctrine does not.

## The Claude Code plugin

The plugin is an add-on to the package, not a second way to install it. It carries no copy of the
engine: its hooks resolve the project's own `doc-marshal` -- `.venv/bin` or `venv/bin` first,
`Scripts/` on Windows, then PATH -- so the agent validates against exactly the version the
repository installed and CI runs. With no engine installed the hooks do nothing, except that the
session-start hook says so once in a project that has a docs tree. `init --claude-code` installs
it through the `claude` CLI, at project scope; nothing else in the tool depends on it being there.

Its value is the two hooks no other harness provides. **PostToolUse** validates a note the moment
it is written: it runs `check --skip-non-notes` on the one file, selects the errors and warnings by
their line prefixes, and returns them as context. It is deliberately non-blocking -- a note can be
legitimately incomplete mid-edit, and a hook that vetoed those would fight the work rather than
check it. **SessionStart** hands the session the [briefing](briefing.md).

`plugin/skills/marshal-the-docs/SKILL.md` is thin: a description good enough for skill matching,
then an instruction to run `doc-marshal info --marshalling` and follow it. The marshalling is
versioned with the engine that enforces it, so the skill does not restate it. Its description
scopes it to the docs tree, so a docstring or README edit does not load it.

## Other agents

`doc-marshal init` writes `AGENTS.md` inside the docs tree by default -- the vendor-neutral
surface, which Claude Code also reads. Either file is descriptive: what the tree, its commands and
its two special files are for, and nothing about how to use them, which is `doc-marshal info`.

`init --claude-code` changes four things:

- it writes `CLAUDE.md` instead of `AGENTS.md`;
- it puts one import line, `@<docs tree>/CLAUDE.md`, in the repository's root `CLAUDE.md`, creating
  that file if there is none. Claude Code loads a nested memory file only once a session reads
  under its directory, so without the import a session that never opens the docs never learns they
  exist. `doctor` reports a docs-tree `CLAUDE.md` the root does not import;
- it allows `Bash(doc-marshal:*)`, `Bash(uv run doc-marshal:*)` and `Bash(.venv/bin/doc-marshal:*)`
  in `.claude/settings.json`, because the bare name alone matches neither of the two spellings a
  session actually uses when the engine is installed among a project's own dependencies;
- it installs the plugin -- `claude plugin marketplace add rootdrew27/doc-marshal --scope project`,
  then `claude plugin install doc-marshal@doc-marshal --scope project`. Both are idempotent and
  both run after the permissions merge, because Claude Code writes the same settings file and owns
  the shape of the keys it writes. Project scope is the point: the enablement lands in the
  repository, so the hooks arrive with a clone. Whatever fails here -- no `claude` on PATH, an
  offline marketplace clone, a CLI that moved -- costs the two printed commands, never the
  initialisation, and `--no-plugin` skips the attempt.

Other harnesses have no import syntax, so plain `init` prints the reference line for the root
`AGENTS.md` and writes nothing there. Supported is Claude Code on macOS and Linux: that is what the
hooks, the import line and the smoke test exercise. The CLI, the pre-commit hook and CI run
anywhere Python does, and the hook lookup and `doctor` probe a Windows virtualenv's `Scripts/`, but
nothing on Windows or in another harness is tested.

## Pre-commit

`.pre-commit-hooks.yaml` declares two entries for the pre-commit framework. `doc-marshal-check`
runs `check --skip-non-notes` on the staged markdown, so it may be handed every markdown file a
change touched. `doc-marshal-index` regenerates `INDEX.md` and passes no filenames.

The framework will not stage what a hook rewrote: a hook that modifies a file fails, and you
re-add. That is how `black`, `ruff-format` and `prettier` behave, so a user meets a failure they
have seen a hundred times rather than a bespoke one, and nothing silently adds files to their
commit. The invariant that matters -- that no pushed branch carries a stale index -- is held by CI
regardless.

`init --pre-commit` never parses YAML. Absent, it writes `.pre-commit-config.yaml`; present, it
detects a doc-marshal entry by substring and prints the block to paste. The file belongs to the
user in a way the generated ones do not, and a YAML reader would have to pass the same
strictness test that blocks a markdown parser -- see `docs/dependency-policy.md`.

## CI

`init --ci` writes `.github/workflows/docs.yml` -- GitHub Actions only -- and where the repository
has no `.github/` it writes nothing and prints the steps instead, for whatever CI does run there. Two properties of that file are the reason the engine owns
it rather than a README snippet:

- **`fetch-depth: 0`.** `drifted` and `--range` answer from a git diff, and the default shallow
  clone makes them answer *nothing* rather than fail: a silent wrong answer from the tool whose
  whole subject is silent staleness.
- **No `paths:` filter.** Half of what the job checks is whether anchors still resolve, and those
  break in the change that renames or deletes the code -- which by definition touches no
  documentation.

The workflow runs on pull requests only, because both ranged steps read
`github.event.pull_request.base.sha`, which is empty on a push. `index --check` runs with
`continue-on-error: true`, so a stale index warns rather than failing the build. Each step calls
`uvx doc-marshal==<minor>.*` directly; there is no composite Action, which would be sugar over a
three-line step.
