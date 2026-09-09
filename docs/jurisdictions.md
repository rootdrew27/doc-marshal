---
type: reference
updated: 2026-09-08
summary: The four places that name an engine version, why absence is legal and disagreement is not, and what doctor and upgrade do about it
code_refs:
  - src/doc_marshal/integrate.py
  - src/doc_marshal/doctor.py
  - src/doc_marshal/upgrade.py
  - src/doc_marshal/manager.py
---

# One version everywhere

**Every jurisdiction that names an engine version names the same one; a jurisdiction may be
absent.** There are four.

| Jurisdiction | Where the version is written | Who writes it |
| --- | --- | --- |
| the project's environment | the installed distribution | the project manager |
| `pyproject.toml` | a specifier on `doc-marshal` | the project manager |
| the pre-commit `rev:` | the `rev:` under this repository's `- repo:` entry in `.pre-commit-config.yaml` | `init --pre-commit`, `upgrade` |
| the CI pin | `doc-marshal==X.Y.*` in any workflow under `.github/workflows/` | `init --ci`, `upgrade` |

Absence is legal: adopting the tree without pre-commit or without CI is supported, and `doctor`
reports `repo pin: none` without complaint. Disagreement is the problem -- an agent would validate
against one version while CI ran another, which is exactly the drift this tool exists to make
visible.

The first two are not written by the engine. `uv add --dev doc-marshal==X.Y.Z` is one command that
writes both, and hand-editing a dependencies table behind a manager's back is how a lockfile stops
matching what is installed.

## What each jurisdiction is allowed to say

`pyproject.toml` pins with `==X.Y.Z`. A `~=`, `>=`, `<`, `!=` or a `*` there admits an environment
the other three do not, so the next resolve can move that one jurisdiction and leave the others
behind. `doctor` reports a range in `pyproject.toml` as a problem even when it currently matches
the running version, because that is a property of the pin itself rather than of today's
agreement.

The CI pin is the deliberate exception: `init --ci` and `upgrade` write `doc-marshal==X.Y.*`, a
minor wildcard, so a patch release reaches CI without a commit. `doctor` holds every pin to
admitting the running version rather than to naming it exactly, and raises the range problem for
`pyproject.toml` alone.

## An engine with no tag

A branch, an editable install or a bare checkout reports a version like any other, but no `v0.4.0`
tag exists for a `rev:` to resolve and no wheel exists for `uvx` to fetch. `released()` reads the
answer from PEP 610's `direct_url.json`, which a distribution installed from a path or a URL
carries and one resolved from an index does not, and it needs no network to do it.

With no tag, `init` writes the jurisdictions it can and says which it skipped and why, rather than
writing a `rev:` that fails on its first run. It offers no snippet to paste in place of the file it
declined to write, for the same reason: an unwritable version pasted by hand is the same broken
`rev:`, one copy later. `init --pin X.Y.Z` writes them regardless, at a version
the caller names: naming it is the caller asserting the tag exists, which is the one thing the
engine cannot check offline.

## What `doctor` reads

`pins()` in `integrate.py` reads all three written jurisdictions -- the pre-commit `rev:`, the
`pyproject.toml` specifier, and every `doc-marshal==` in every workflow -- deduplicated, so a
workflow naming its pin once per step reports once. Reading and writing live in one module, so
what `doctor` checks and what `init` and `upgrade` write can never be two different answers.

`doctor` prints the running version and where it came from, the interpreter, the docs tree, whether
the root `CLAUDE.md` imports the docs-tree one, the engine in the project's virtualenv -- the one
the plugin's hooks run -- the engine on PATH, and every repository pin with whether it matches. No
integration runs it: the pull-request workflow runs `check`, `index --check` and `drifted` and
nothing else, so a disagreement surfaces when someone asks. It exits 1 having reported any of:

- no docs tree resolves here, so nothing is being validated;
- no engine in the project's virtualenv or on PATH, so the plugin's hooks run nothing;
- the virtualenv or PATH engine reporting a different version from this run;
- a pin that does not admit the running version, or that does not admit the virtualenv's engine;
- a range in `pyproject.toml`;
- a docs-tree `CLAUDE.md` the root `CLAUDE.md` does not import.

## What `upgrade` does

`doc-marshal upgrade X.Y.Z` drives the install and then moves the pins, in two phases, because the
engine that starts an upgrade is the *old* one.

Phase one detects the project manager -- `uv.lock`, then `poetry.lock`, then a `[tool.*]` table,
then pip -- and installs. Only `uv` is driven, with `uv add --dev doc-marshal==X.Y.Z`, the one
command that writes the environment and the specifier together; the exact pin is the point, since
`uv add doc-marshal` alone writes a range. Any other manager is handed its two commands and stops.
It then finds the executable that reports the new version, in the virtualenv or on PATH, and
re-runs *that* as `upgrade X.Y.Z --pins`. If nothing reporting the new version is resolvable it
stops rather than writing pins from the old engine: an upgrade that visibly stopped half done
beats one that reports success in the old version's words.

Phase two rewrites the pre-commit `rev:` and every workflow pin, then runs `doctor` and
`check --all`, so the repository is never left between two versions with its own `doctor` failing.
`--pins` runs phase two alone; `--dry-run` says what would change and writes nothing.

Two things it says out loud every time:

- **`pre-commit autoupdate` moves the `rev:` on its own** and nothing else, which is precisely the
  disagreement `doctor` reports. `upgrade` is the route that moves every jurisdiction at once.
- **A minor release may enforce policies the old one did not**, so a tree that passed yesterday can
  fail today. That is why `check --all` runs as part of an upgrade rather than surprising you
  after it.
