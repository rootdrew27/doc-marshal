"""`doc-marshal doctor`: which engine is running, which ones the repository carries, and whether
they agree.

The stability contract (see docs/engine.md) holds only while every route to the engine resolves
the same version: the one on PATH, the one in the project's virtualenv that the plugin's hooks
run, and the one the repository pins in its pre-commit config, its pyproject or its CI workflow.
This command reports each and exits 1 on a mismatch -- an agent validating at 0.6 while CI runs
0.5 is the failure it exists to make visible.

The jurisdictions themselves are read in `integrate`, which also writes them, so what `doctor`
checks and what `init` and `upgrade` write can never be two different answers (see
docs/jurisdictions.md).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__
from .config import add_docs_tree_option
from .discovery import cwd_repo, find_docs_tree, find_repo_root
from .errors import DocMarshalError
from .init import has_import, import_line
from .integrate import PRECOMMIT, PYPROJECT, is_exact, normalize, pin_matches, pins
from .paths import rel_to
from .settings import SETTINGS

VENV_DIRS = (".venv", "venv")


def version_of(exe: str) -> str | None:
    """The version an executable reports, or None when it does not run."""
    try:
        result = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"(\d+\.\d+\S*)", result.stdout)
    return match.group(1) if match else None


def on_path() -> tuple[str, str | None] | None:
    """The `doc-marshal` executable on PATH and the version it reports, or None when there is none."""
    exe = shutil.which("doc-marshal")
    if exe is None:
        return None
    return exe, version_of(exe)


def in_venv(repo_root: Path) -> tuple[Path, str | None] | None:
    """The engine in the project's virtualenv -- the one the plugin's hooks resolve first."""
    for venv in VENV_DIRS:
        for exe in (repo_root / venv / "bin" / "doc-marshal", repo_root / venv / "Scripts" / "doc-marshal.exe"):
            if exe.is_file() and os.access(exe, os.X_OK):
                return exe, version_of(str(exe))
    return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="doc-marshal doctor", description="Report every resolvable engine and flag a version mismatch."
    )
    add_docs_tree_option(parser)
    args = parser.parse_args(argv)

    problems: list[str] = []
    print(f"running:   doc-marshal {__version__} from {Path(__file__).resolve().parent}")
    print(f"python:    {sys.version.split()[0]} at {sys.executable}")

    docs_tree: Path | None = None
    try:
        docs_tree = find_docs_tree(args.docs_tree)
        repo_root = find_repo_root(docs_tree)
        print(f"docs tree: {rel_to(docs_tree, repo_root)}/ under {repo_root} (config {SETTINGS.config_name})")
    except DocMarshalError as exc:
        _, repo_root, _ = cwd_repo()
        print(f"docs tree: none -- {exc.args[0].splitlines()[0]}")
        problems.append("no docs tree resolves here, so nothing is being validated")

    # A docs-tree CLAUDE.md is what `init --claude-code` writes, and it reaches a session only
    # through the import line in the root CLAUDE.md. A nested memory file with no import is loaded
    # only once a session reads under the docs tree, so the pointer exists and nobody sees it.
    if docs_tree is not None and (docs_tree / "CLAUDE.md").is_file():
        label = rel_to(docs_tree, repo_root).as_posix()
        line = import_line(label, "CLAUDE.md")
        if has_import(repo_root / "CLAUDE.md", line):
            print(f"root file: CLAUDE.md imports {label}/CLAUDE.md (every session sees the pointer)")
        else:
            print(f"root file: CLAUDE.md does not import {label}/CLAUDE.md")
            problems.append(
                f"{label}/CLAUDE.md exists but the root CLAUDE.md does not import it -- add the line "
                f"`{line}` (doc-marshal init --claude-code writes it)"
            )

    venv_entry = in_venv(repo_root)
    if venv_entry is None:
        print(f"venv:      no {'/'.join(VENV_DIRS)} engine (the plugin's hooks fall back to PATH)")
    else:
        exe, version = venv_entry
        print(f"venv:      {rel_to(exe, repo_root)} -- {version or 'version unknown'} (what the plugin's hooks run)")
        if version and normalize(version) != __version__:
            problems.append(f"the project's virtualenv has doc-marshal {version} but this run is {__version__}")

    path_entry = on_path()
    if path_entry is None:
        print("on PATH:   none" + ("" if venv_entry else " (the plugin's hooks have nothing to run)"))
        if venv_entry is None:
            problems.append("no engine in the project's virtualenv or on PATH -- the plugin's hooks run nothing")
    else:
        path_exe, version = path_entry
        print(f"on PATH:   {path_exe} -- {version or 'version unknown'}")
        if version and normalize(version) != __version__:
            problems.append(f"PATH resolves doc-marshal {version} but this run is {__version__}")

    # Every jurisdiction that names a version names the same one; a jurisdiction may be absent.
    # Absence is not a problem -- adopting the tree without pre-commit or CI is supported -- but
    # disagreement is.
    repo_pins = pins(repo_root)
    if not repo_pins:
        print("repo pin:  none (`doc-marshal init --pre-commit --ci` writes both)")
    for where, pin in repo_pins:
        ok = pin_matches(pin, __version__)
        print(f"repo pin:  {where} pins {pin} -- {'matches' if ok else 'DOES NOT MATCH'} the running {__version__}")
        if not ok:
            problems.append(f"{where} pins {pin}, this run is {__version__}")
        if venv_entry and venv_entry[1] and not pin_matches(pin, venv_entry[1]):
            problems.append(
                f"the project's virtualenv has {venv_entry[1]} but {where} pins {pin}: an agent "
                "would validate against one version and CI against another"
            )

    # Agreeing today is not the whole invariant: a range in the dependency table admits versions
    # the `rev:` and the CI pin do not, so the next resolve can move that one jurisdiction and
    # leave the others behind. That is a property of the pin itself, not of whether the
    # jurisdictions match now.
    for where, pin in repo_pins:
        if where == PYPROJECT and not is_exact(pin):
            problems.append(
                f"{PYPROJECT} pins {pin}, a range: the next resolve may install a version the "
                f"{PRECOMMIT} rev and the CI pin do not name. `doc-marshal upgrade {__version__}` "
                "moves every jurisdiction to one version"
            )

    print()
    if problems:
        for problem in problems:
            print(f"PROBLEM: {problem}")
        return 1
    print("ok: every resolvable copy of the engine agrees")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
