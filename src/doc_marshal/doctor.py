"""`doc-marshal doctor`: which engine is running, which ones the repository carries, and whether
they agree.

The stability contract (SPEC.md section 13) holds only while every route to the engine resolves
the same version: the one on PATH, the one in the project's virtualenv that the plugin's hooks
run, and the one the repository pins in its pre-commit config or pyproject. This command reports
each and exits 1 on a mismatch -- an agent validating at 0.6 while CI runs 0.5 is the failure it
exists to make visible.
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
from .paths import DocMarshalError, find_docs_root, find_repo_root, git_toplevel, rel_to
from .settings import SETTINGS

VENV_DIRS = (".venv", "venv")


def running_from() -> str:
    """Where this module was imported from."""
    return str(Path(__file__).resolve().parent)


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
        exe = repo_root / venv / "bin" / "doc-marshal"
        if exe.is_file() and os.access(exe, os.X_OK):
            return exe, version_of(str(exe))
    return None


def repo_pins(repo_root: Path) -> list[tuple[str, str]]:
    """Every version the repository pins doc-marshal to, as (where, version)."""
    pins: list[tuple[str, str]] = []
    config = repo_root / ".pre-commit-config.yaml"
    if config.is_file():
        current_repo = ""
        for line in config.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("- repo:"):
                current_repo = stripped
            elif stripped.startswith("rev:") and "doc-marshal" in current_repo:
                pins.append((".pre-commit-config.yaml", stripped.split(":", 1)[1].strip().strip("\"'")))
    pyproject = repo_root / "pyproject.toml"
    if pyproject.is_file():
        for match in re.finditer(r"doc-marshal\s*(==|~=|>=)\s*([\w.*]+)", pyproject.read_text(encoding="utf-8")):
            pins.append(("pyproject.toml", f"{match.group(1)}{match.group(2)}"))
    return pins


def normalize(version: str) -> str:
    return version.lstrip("vV")


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


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="doc-marshal doctor", description="Report every resolvable engine and flag a version mismatch."
    )
    parser.add_argument("--docs-root", help="docs root (default: the directory holding the marker)")
    args = parser.parse_args(argv)

    problems: list[str] = []
    print(f"running:   doc-marshal {__version__} from {running_from()}")
    print(f"python:    {sys.version.split()[0]} at {sys.executable}")

    try:
        docs_root = find_docs_root(args.docs_root)
        repo_root = find_repo_root(docs_root)
        print(f"docs root: {rel_to(docs_root, repo_root)}/ under {repo_root} (marker {SETTINGS.marker_name})")
    except DocMarshalError as exc:
        repo_root = git_toplevel(Path.cwd()) or Path.cwd()
        print(f"docs root: none -- {exc.args[0].splitlines()[0]}")

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
    else:
        exe, version = path_entry
        print(f"on PATH:   {exe} -- {version or 'version unknown'}")
        if version and normalize(version) != __version__:
            problems.append(f"PATH resolves doc-marshal {version} but this run is {__version__}")

    pins = repo_pins(repo_root)
    if not pins:
        print("repo pin:  none (pin with pre-commit `rev:` or `uvx doc-marshal==X.Y.*` in CI)")
    for where, pin in pins:
        ok = pin_matches(pin, __version__)
        print(f"repo pin:  {where} pins {pin} -- {'matches' if ok else 'DOES NOT MATCH'} the running {__version__}")
        if not ok:
            problems.append(f"{where} pins {pin}, this run is {__version__}")
        if venv_entry and venv_entry[1] and not pin_matches(pin, venv_entry[1]):
            problems.append(
                f"the project's virtualenv has {venv_entry[1]} but {where} pins {pin}: an agent "
                "would validate against one version and CI against another"
            )

    print()
    if problems:
        for problem in problems:
            print(f"MISMATCH: {problem}")
        return 1
    print("ok: every resolvable copy of the engine agrees")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
