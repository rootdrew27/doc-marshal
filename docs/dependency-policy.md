---
type: reference
updated: 2026-09-08
summary: The tests a runtime library must pass before this package takes one, and the one route into the engine that taking one breaks
code_refs:
  - pyproject.toml
  - plugin/hooks/_engine.py
---

# Runtime dependencies

`pyproject.toml` declares `dependencies = []` today, and that is a standard rather than a vow.
Runtime libraries are permitted, and one is taken when it passes all four tests below. Nothing has
passed them yet.

## The four tests

| Test | What it asks |
| --- | --- |
| 1. It installs with no compiler | pure Python, or a universal wheel, on every supported Python. `requires-python` is `>=3.11`; CI installs and exercises the package on 3.11 through 3.14, and the publish workflow installs the built wheel into a clean environment before anything is published. What breaks this is usually a transitive library rather than the one being added, so it is checked rather than asserted |
| 2. It must not replace a strictness boundary | see below |
| 3. It is not on the `check` import graph | or it is imported lazily so that it is not. `cli.py` dispatches every verb through `importlib.import_module`, so a library is imported by the one verb that needs it and never from `__init__.py` or `cli.py`. The cost is paid per note, not per session: the PostToolUse hook runs the engine on every write, and pre-commit on every commit |
| 4. It earns a decision note | the trade is recorded where it can be reopened |

## Test 2 blocks the obvious candidates

**PyYAML.** `parse_frontmatter` deliberately reads a subset -- scalars and dash-item lists -- and
raises on anything richer, so a block the convention does not sanction fails loudly instead of
validating as empty. PyYAML accepts nested mappings, flow style, anchors, and the Norway problem
where a bare `no` becomes `False`. The strictness is the convention, enforced at parse time.

A subset parser polices the inside of its subset and cannot see the outer boundary. It accepted,
for a while, a summary carrying an unquoted `: ` -- ordinary English, and a nested mapping to every
real YAML parser, which refused those notes wherever the tree was read from outside this package.
The boundary is now enforced on both sides in `frontmatter.py`, and `scripts/smoke.sh` reads every
note a second time with PyYAML and compares the two readings, so "the subset is a subset" is
checked on every run rather than asserted here. That is what a development library buys without
any of test 2's cost.

**A real markdown parser.** The same argument. The heading, section and table readers in
`markdown.py` are strict subset readers, and the structure and vocabulary policies depend on
exactly what they refuse.

Whether test 2 survives contact with a library worth having is left to that library's decision
note rather than settled in the abstract.

`tomli-w` and `pyyaml` are taken as development libraries -- the first for the round-trip test
between the profile and its TOML form, the second for the differential check above. They sit in the
`dev` group beside `pytest`, `ruff` and `mypy`, and neither is imported at runtime: the differential
check imports the `check` verb first and asserts that no `yaml` arrived with it, and CI installs
PyYAML alongside the package rather than as part of it.

## The hooks are standard-library only, permanently

The plugin's hooks are not covered by any of this, and never will be. They run on the user's
ambient `python3` -- the one interpreter this project does not control -- so nothing above applies
to them. Two boundaries hold the separation:

- A hook never imports `doc_marshal`. It resolves the console script and runs it as a subprocess.
- It selects the errors and warnings it reports on the line prefixes `report.py` publishes, not on
  an imported symbol, which keeps it independent of which engine it resolved and of that engine's
  Python.

`scripts/smoke.sh` exercises both, running each hook with `PATH` stripped to `/usr/bin:/bin`.

## The one route a library breaks

Every route into the engine resolves its own libraries -- a project virtualenv, `uv run`,
`uv tool install`, `uvx`, and pre-commit's `language: python`, which builds an isolated
environment from `pyproject.toml`. The plugin's hooks run a resolved console script, so a library
is resolved on the far side of a boundary the hook cannot see across, and no hook changes to
permit one.

The exception is `python3 -m doc_marshal` from a bare checkout. It was never a hook route -- the
hooks look only for the console script -- so the cost falls on a human reading the README, and the
replacement is `uvx doc-marshal` for someone who has installed nothing, or `uv run doc-marshal`
from a checkout, which syncs the exact versions in `uv.lock`. `__main__.py` stays, so the package still runs
from a checkout with nothing installed for as long as that keeps working.
