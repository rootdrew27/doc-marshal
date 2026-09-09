---
type: runbook
updated: 2026-09-08
summary: Install doc-marshal into a repository, mark its docs tree, wire the integrations, and move every pin to a new version
code_refs:
  - src/doc_marshal/init.py
  - src/doc_marshal/upgrade.py
---

# Set up doc-marshal in a repository

## Prerequisites

- A git repository. Git is not optional: anchor paths must be tracked, and the change a run is
  scoped to is a diff.
- Python 3.11 or later.
- `uv` on PATH for the steps below. Any other manager works; see step 6.
- The version to install, written as `X.Y.Z` throughout. Replace it with a published release --
  for example `uv add --dev doc-marshal==0.4.0`. In a repository that already names a version, use
  that one and not the latest release.

## Steps

1. **Install the engine into the project's environment**, where the plugin's hooks look:

   ```bash
   uv add --dev doc-marshal==X.Y.Z
   ```

   uv prints its resolution and the packages it installed, and writes both the specifier in
   `pyproject.toml` and the environment in `.venv/`. A repository that is not a Python project has
   no table to add to; put the engine on PATH instead with `uv tool install doc-marshal==X.Y.Z`.

2. **Mark the docs tree and wire the integrations:**

   ```bash
   uv run doc-marshal init --claude-code --pre-commit --ci
   ```

   It prints a `created:` table -- one row per file, with what that file does there:
   `docs/.doc-marshal.toml`, `docs/NOMENCLATURE.md`, `docs/CLAUDE.md`, the `@docs/CLAUDE.md` import
   in the root `CLAUDE.md`, `docs/INDEX.md`, `.claude/settings.json`, `.pre-commit-config.yaml` and
   `.github/workflows/docs.yml` -- then numbered `next:` steps. An integration no flag asked for is
   named under `not wired yet:`, one line for the flag that writes it, rather than printed as a
   config block to paste at a version you would have to fill in yourself.

   `--claude-code` also installs the Claude Code plugin, through `claude plugin marketplace add`
   and `claude plugin install --scope project`. Both are idempotent, and project scope puts the
   enablement in this repository's own `.claude/settings.json`, so a clone gets the hooks rather
   than each person who remembers to run `/plugin`. With no `claude` on PATH the two commands are
   printed instead, and `--no-plugin` skips them.

   Drop `--claude-code` for the vendor-neutral `AGENTS.md`; `init` then prints the one reference
   line to add to the root file yourself. `init <path>` marks a directory other than `docs/`.

   If it says the engine did not come from a release, it declined to write a `rev:` that would not
   resolve. Re-run it naming a published version: `init --pre-commit --ci --pin X.Y.Z`.

3. **Fill in the shared vocabulary.** `docs/NOMENCLATURE.md` is scaffolded with an empty table.
   Add one row per term the project uses inconsistently -- the term, a one-line definition, and the
   aliases it rules out. Every session is handed this file, and every other note is scanned against
   its `Avoid` column.

4. **Stage the anchored code, then validate:**

   ```bash
   git add -A
   uv run doc-marshal check --all
   ```

   A clean tree prints `N notes checked -- 0 error(s), 0 warning(s)` and exits 0. An anchor to a
   file git does not track is an error, which is why the `git add` comes first.

5. **Confirm every route to the engine agrees:**

   ```bash
   uv run doc-marshal doctor
   ```

   It lists the running engine, the interpreter, the docs tree, the engine in `.venv/`, the engine
   on PATH and every version the repository names, then `ok: every resolvable copy of the engine
   agrees`. Anything it prefixes with `PROBLEM:` exits 1; fix it before relying on the hooks.

6. **If the project does not use `uv`**, install by hand and run steps 2 to 5 unchanged. Nothing
   after the install cares which manager put the engine there. What matters is *where* it lands:
   the plugin's hooks look in `.venv/` and `venv/` first, then PATH, and an engine anywhere else
   leaves them running nothing -- which reads exactly like a clean tree.

   | The project uses | Install with | Hooks find it |
   | --- | --- | --- |
   | pip with a virtualenv in the tree | `pip install doc-marshal==X.Y.Z` | yes, `.venv/` or `venv/` |
   | Poetry with `virtualenvs.in-project true` | `poetry add --group dev doc-marshal==X.Y.Z` | yes, `.venv/` |
   | Poetry with the default environment | -- | **no**: turn on in-project virtualenvs and reinstall, or install to PATH |
   | nothing in particular | `uv tool install doc-marshal==X.Y.Z` | yes, PATH |

7. **To move to a new version later**, run one command rather than upgrading anything by hand:

   ```bash
   uv run doc-marshal upgrade X.Y.Z
   ```

   It installs the version, re-runs itself as the engine it just installed, rewrites the pre-commit
   `rev:` and every CI pin, then prints `doctor` and `check --all`. `--dry-run` says what it would
   do; `--pins` does the second half alone, after an install a manager it does not drive performed.

   Never use `pre-commit autoupdate` to move this version: it moves the `rev:` alone and leaves the
   other three [jurisdictions](jurisdictions.md) behind, which is the disagreement `doctor` exists
   to report.
