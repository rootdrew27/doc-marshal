---
type: runbook
updated: 2026-09-07
summary: Cut a doc-marshal release: bump the version, regenerate the derived copies, run the checks, merge, and tag to publish
code_refs:
  - scripts/sync_version.py
  - scripts/render_doctrine.py
  - .github/workflows/publish.yml
---

# Cut a doc-marshal release

## Prerequisites

- `main` is green: `.github/workflows/test.yml` passing on its latest commit.
- A release branch off `main`. Nothing here is done on `main` directly.
- The development group synced: `uv sync --group dev`.
- Push rights on the repository, and PyPI's trusted publisher already configured for
  `publish.yml` in the `pypi` environment. It is configured once, not per release.
- The version to release, as `X.Y.Z`. A release that adds a policy is a minor, because a tree that
  passed before can fail after.

## Steps

1. **Bump the version.** `__version__` in `src/doc_marshal/__init__.py` is the one source;
   `pyproject.toml` reads it through hatch, and every other copy is derived.

   ```bash
   uv run python scripts/sync_version.py --set X.Y.Z
   ```

   It prints `wrote src/doc_marshal/__init__.py`, then one `wrote` line per derived copy it
   changed -- `plugin/.claude-plugin/plugin.json`, `README.md`, `.pre-commit-hooks.yaml` -- and
   rewrites the README's two generated snippets from the same functions `init --pre-commit --ci`
   writes files with.

2. **Regenerate the rendered doctrine**, which is what a reviewer without the CLI reads:

   ```bash
   uv run python scripts/render_doctrine.py
   ```

   It prints `wrote rendered/<name>` for each file that changed, and nothing when they are already
   current.

3. **Confirm nothing is left behind:**

   ```bash
   uv run python scripts/sync_version.py --check
   uv run python scripts/render_doctrine.py --check
   ```

   Each prints one confirming line and exits 0. `sync_version.py --check` naming a copy is the
   build refusing to proceed -- a tag must never publish a wheel that reports a different version
   from its name.

4. **Run what CI runs**, cheapest first:

   ```bash
   uv run ruff check
   uv run ruff format --check
   uv run mypy
   PLUGIN=$PWD/plugin uv run bash scripts/smoke.sh
   ```

   The smoke test builds a throwaway repository, exercises every verb end to end, and runs both
   plugin hooks with `PATH` stripped. It is `set -eux`, so the first failing line is the last one
   printed.

5. **Open a pull request** and let it go green. `.github/workflows/test.yml` repeats the smoke run on
   Python 3.11 through 3.14, checks `rendered/`, and runs ruff, mypy and the version check.

6. **Merge to `main`.** The `render` workflow regenerates `rendered/` on the push and commits it
   back if it differs, so the copy stays derived rather than maintained.

7. **Tag the merge commit and push the tag.** The tag is the release:

   ```bash
   git checkout main && git pull
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

8. **Watch `publish.yml`.** It refuses the build unless the tag matches `__version__` and
   `sync_version.py --check` passes, builds the wheel, installs it into a clean environment and
   runs `doc-marshal --version` and `info --marshalling` from there, then publishes to PyPI by
   trusted publishing -- no token is stored anywhere. A failure at the first step means step 3 was
   skipped. Nothing was published, so fix it on a branch, merge, and move the tag onto the new
   commit:

   ```bash
   git tag -d vX.Y.Z && git push origin :refs/tags/vX.Y.Z
   git tag vX.Y.Z && git push origin vX.Y.Z
   ```

9. **Move this repository's own pins to the new release**, so the tree that documents the engine
   is validated by it:

   ```bash
   uv run doc-marshal upgrade X.Y.Z
   ```
