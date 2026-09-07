"""The repository's integration files, and the version they name.

Four facets name a version: the project's environment, `pyproject.toml`, the pre-commit `rev:`,
and the CI pin. **Every facet that names a version names the same one; a facet may be absent**
(SPEC.md section 19). `doctor` reads them, `init` writes them and `upgrade` rewrites them -- so
reading and writing live in one module. A reader and a writer that drifted apart would put the
disagreement this tool exists to catch inside the tool that catches it.

Two facets are not written here. The environment and `pyproject.toml` belong to the project
manager: `uv add --dev doc-marshal==X.Y.Z` is one command that writes both, and hand-editing a
dependency table behind a manager's back is how a lockfile stops matching what is installed.

No YAML parser. The pre-commit config and the CI workflow are read and rewritten by line, the way
`doctor` has always read them: the dependency policy of section 9 rules out a parser for this, and
`.pre-commit-config.yaml` belongs to the user in a way the generated files do not -- when it
already exists, this module prints a block to paste and touches nothing.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from importlib.metadata import Distribution, PackageNotFoundError
from pathlib import Path
from typing import NamedTuple

from . import __version__

REPO_URL = "https://github.com/rootdrew27/doc-marshal"
PRECOMMIT = ".pre-commit-config.yaml"
PYPROJECT = "pyproject.toml"
WORKFLOWS = Path(".github") / "workflows"
CI_FILE = "docs.yml"

# The pin as each file spells it: a pre-commit `rev: v0.3.0`, a pyproject specifier, a `uvx
# doc-marshal==0.3.*` in a workflow step.
PYPROJECT_PIN = re.compile(r"doc-marshal\s*(==|~=|>=)\s*([\w.*]+)")
CI_PIN = re.compile(r"(doc-marshal==)([\w.*]+)")


class Pin(NamedTuple):
    """A version some file in the repository names, and where it names it."""

    where: str
    spec: str


class Outcome(NamedTuple):
    """What a writer did: a line for `init`'s "wrote" list, or a note to print instead."""

    written: str | None = None
    note: str | None = None


def minor(version: str) -> str:
    return ".".join(version.split(".")[:2])


def normalize(version: str) -> str:
    return version.lstrip("vV")


def is_exact(spec: str) -> bool:
    """Whether a pin admits exactly one version. `~=` and `>=` admit an environment the other
    facets do not, which is the mismatch the invariant exists to prevent."""
    spec = normalize(spec)
    return not spec.startswith(("~=", ">=", "<", "!=")) and "*" not in spec


def pin_matches(pin: str, version: str) -> bool:
    """Whether a pin like `==0.5.*`, `>=0.5`, `~=0.5.0` or `v0.5.0` admits `version`."""
    pin = normalize(pin)
    if pin.startswith("=="):
        pattern = pin[2:]
        if pattern.endswith(".*"):
            return version.startswith(pattern[:-1])
        return version == pattern
    if pin.startswith("~="):
        base = pin[2:].split(".")
        return version.split(".")[: max(len(base) - 1, 1)] == base[: max(len(base) - 1, 1)]
    if pin.startswith(">="):
        return tuple(int(p) for p in re.findall(r"\d+", version)) >= tuple(int(p) for p in re.findall(r"\d+", pin))
    return version == pin


def released() -> bool:
    """Whether this engine came from a published release, so a `rev:` tag and a `uvx` pin exist
    for it.

    An editable install, a path install or a bare checkout reports a version like any other, and
    writing `rev: v0.4.0` for a tag that was never pushed gives a pre-commit hook that cannot
    resolve. PEP 610 records the answer: a distribution installed from a direct URL carries
    `direct_url.json`, one resolved from an index does not.
    """
    try:
        return Distribution.from_name("doc-marshal").read_text("direct_url.json") is None
    except (PackageNotFoundError, OSError):
        return False


def writable(pin: str | None) -> str | None:
    """The version the integration files may name, or None when nothing here can be vouched for.

    A pin the caller named is the caller asserting the tag exists, which is the one thing this
    module cannot check offline. Absent one, the running version is safe only if it came from a
    release. Resolved once, by the caller, so that the writers and the advice `init` prints when it
    writes nothing are gated on the same answer instead of each asking again -- an unwritable
    version printed as a snippet to paste is the same broken `rev:`, one copy later.
    """
    if pin:
        return normalize(pin)
    return __version__ if released() else None


# --- reading the facets -------------------------------------------------------------------------


def workflow_files(repo_root: Path) -> list[Path]:
    """Every GitHub Actions workflow, in a stable order."""
    directory = repo_root / WORKFLOWS
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.iterdir() if p.suffix in (".yml", ".yaml") and p.is_file())


def _revs(lines: list[str]) -> Iterator[tuple[int, str]]:
    """Each `rev:` line belonging to this repository's `- repo:` entry, as (index, version).

    The one rule for finding the pin, so that `pins` reading it and `set_pins` rewriting it cannot
    come to different conclusions about which line is doc-marshal's.
    """
    current_repo = ""
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("- repo:"):
            current_repo = stripped
        elif stripped.startswith("rev:") and "doc-marshal" in current_repo:
            yield i, stripped.split(":", 1)[1].strip().strip("\"'")


def _precommit_pins(repo_root: Path) -> list[Pin]:
    config = repo_root / PRECOMMIT
    if not config.is_file():
        return []
    return [Pin(PRECOMMIT, rev) for _, rev in _revs(config.read_text(encoding="utf-8").splitlines())]


def pins(repo_root: Path) -> list[Pin]:
    """Every version the repository pins doc-marshal to, deduplicated.

    A workflow names its pin once per step, so the same pin is found three times in the file the
    README tells people to write. Reporting it three times would say nothing the first row did not.
    """
    found = list(_precommit_pins(repo_root))
    pyproject = repo_root / PYPROJECT
    if pyproject.is_file():
        for match in PYPROJECT_PIN.finditer(pyproject.read_text(encoding="utf-8")):
            found.append(Pin(PYPROJECT, f"{match.group(1)}{match.group(2)}"))
    for workflow in workflow_files(repo_root):
        where = (WORKFLOWS / workflow.name).as_posix()
        for match in CI_PIN.finditer(workflow.read_text(encoding="utf-8")):
            found.append(Pin(where, f"=={match.group(2)}"))
    return list(dict.fromkeys(found))


def has_hook(repo_root: Path) -> bool:
    """Whether `.pre-commit-config.yaml` already names this repository. Substring, not YAML: the
    question is only whether writing the block again would duplicate an entry."""
    config = repo_root / PRECOMMIT
    return config.is_file() and "doc-marshal" in config.read_text(encoding="utf-8")


# --- the files, generated from the running version ----------------------------------------------


def precommit_block(version: str, indent: str = "  ") -> str:
    """The `repos:` entry, indented to sit under an existing `repos:` key."""
    lines = [
        f"- repo: {REPO_URL}",
        f"  rev: v{version}",
        "  hooks:",
        "    - id: doc-marshal-check",
        "    - id: doc-marshal-index",
    ]
    return "".join(f"{indent}{line}\n" for line in lines)


def precommit_text(version: str) -> str:
    return "repos:\n" + precommit_block(version)


def ci_steps(version: str) -> list[str]:
    """The steps that validate a docs tree on a pull request, as a workflow spells them.

    The README carries the same steps as a snippet for a repository that already has a workflow;
    `scripts/sync_version.py --check` holds the two in step.
    """
    pin = f"doc-marshal=={minor(version)}.*"
    base = "${{ github.event.pull_request.base.sha }}"
    return [
        "- uses: actions/checkout@v4\n  with:\n    fetch-depth: 0\n",
        "- uses: astral-sh/setup-uv@v6\n",
        f'- run: uvx {pin} check --all --format github --range "{base}..HEAD"\n',
        f"- run: uvx {pin} index --check\n  continue-on-error: true\n",
        f'- run: uvx {pin} affected --range "{base}..HEAD" --format github\n',
    ]


def render_steps(version: str, indent: str) -> str:
    """`ci_steps` as one indented block: under `steps:` in the workflow, under `next:` when `init`
    prints what it did not write. Two indents, one rendering."""
    return "".join(
        f"{indent}{line}\n" if line.strip() else "\n" for step in ci_steps(version) for line in step.splitlines()
    )


def ci_text(version: str) -> str:
    """`.github/workflows/docs.yml`.

    Pull requests only. Both `--range` steps read `github.event.pull_request.base.sha`, which is
    empty on a push, and `--range "..HEAD"` is an exit-2 error rather than a skipped check.
    """
    return f"""\
# Generated by `doc-marshal init --ci`. Validates the docs tree on every pull request.
#
# No `paths:` filter: half of what this checks is whether the anchors still resolve, and those
# break in the change that renames or deletes the code -- which by definition touches no
# documentation. `fetch-depth: 0` because `affected` and `--range` answer from a git diff, and the
# default shallow clone makes them answer *nothing* rather than fail.
#
# The pin is the same version the pre-commit `rev:` and the project environment name. Change it
# with `doc-marshal upgrade <version>`, which moves every facet at once.
name: docs

on:
  pull_request:

permissions:
  contents: read

jobs:
  doc-marshal:
    runs-on: ubuntu-latest
    steps:
{render_steps(version, indent="      ")}"""


# --- writing them -------------------------------------------------------------------------------


def _untagged(what: str) -> Outcome:
    return Outcome(
        note=f"{what} not written: this engine did not come from a release, so `v{__version__}` is "
        "not a tag that resolves and the file would fail on its first run. Name a published "
        "version instead -- `doc-marshal init --pin X.Y.Z` -- or run this from an installed release."
    )


def write_precommit(repo_root: Path, version: str | None) -> Outcome:
    """Write `.pre-commit-config.yaml`, or print the block to paste into the one that exists.

    `version` is None when nothing names this engine (see `writable`): there is no `rev:` that
    would resolve, so nothing is written and the caller is told what to pass instead.
    """
    if version is None:
        return _untagged(PRECOMMIT)
    config = repo_root / PRECOMMIT
    if not config.is_file():
        config.write_text(precommit_text(version), encoding="utf-8")
        return Outcome(written=f"{PRECOMMIT}  (check on staged notes, and the index, at every commit)")
    if has_hook(repo_root):
        return Outcome(note=f"{PRECOMMIT} already names doc-marshal -- left alone")
    return Outcome(
        note=f"{PRECOMMIT} exists and is yours to edit. Add this under `repos:`:\n\n"
        + precommit_block(version, indent="    ")
    )


def write_ci(repo_root: Path, version: str | None) -> Outcome:
    """Write `.github/workflows/docs.yml`, where the repository uses GitHub Actions."""
    if version is None:
        return _untagged((WORKFLOWS / CI_FILE).as_posix())
    if not (repo_root / ".github").is_dir():
        return Outcome(
            note="--ci writes GitHub Actions and this repository has no .github/ -- skipped. The "
            "three commands to run on a pull request are printed above."
        )
    workflow = repo_root / WORKFLOWS / CI_FILE
    label = (WORKFLOWS / CI_FILE).as_posix()
    if workflow.is_file():
        return Outcome(note=f"{label} already exists -- left alone")
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text(ci_text(version), encoding="utf-8")
    return Outcome(written=f"{label}  (check --all, index --check and affected on every pull request)")


def set_pins(repo_root: Path, version: str) -> list[str]:
    """Point every written facet at `version`. Returns one line per file changed.

    The environment and `pyproject.toml` are not here: the project manager wrote those, in the
    step that installed this engine.
    """
    changed: list[str] = []
    config = repo_root / PRECOMMIT
    if config.is_file():
        lines = config.read_text(encoding="utf-8").splitlines(keepends=True)
        edited = False
        for i, _ in _revs(lines):
            line = lines[i]
            replacement = line[: len(line) - len(line.lstrip())] + f"rev: v{version}\n"
            if replacement != line:
                lines[i] = replacement
                edited = True
        if edited:
            config.write_text("".join(lines), encoding="utf-8")
            changed.append(f"{PRECOMMIT}  (rev: v{version})")
    pin = f"{minor(version)}.*"
    for workflow in workflow_files(repo_root):
        text = workflow.read_text(encoding="utf-8")
        updated = CI_PIN.sub(rf"\g<1>{pin}", text)
        if updated != text:
            workflow.write_text(updated, encoding="utf-8")
            changed.append(f"{(WORKFLOWS / workflow.name).as_posix()}  (doc-marshal=={pin})")
    return changed
