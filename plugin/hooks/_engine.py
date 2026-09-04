"""Resolve the `doc-marshal` a hook runs: the project's virtualenv first, then PATH.

The plugin is an add-on to the package, not a distribution of it. It carries no copy of the
engine, so a project is validated by exactly the version it installed -- the one its CI and
pre-commit hooks run -- and never by a second version that happened to arrive with the plugin.
With no engine installed the hooks do nothing, except that the session-start hook says so once
in a project that has a docs root (`MISSING_ENGINE`), because silence there would look like a
clean tree.

Standard library only: this runs on a bare `python3`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parent.parent)
PROJECT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()
MARKER = ".doc-marshal.toml"
VENV_DIRS = (".venv", "venv")
_PRUNE = {".git", ".venv", "venv", "node_modules", "__pycache__", ".claude", ".github"}
_MAX_DEPTH = 4

MISSING_ENGINE = (
    f"doc-marshal: this project has a docs root ({MARKER}) but no `doc-marshal` was found in "
    f"{' or '.join(f'{d}/bin' for d in VENV_DIRS)} (Scripts/ on Windows) or on PATH, so notes are not being validated as "
    "they are written. Install it into the project (`pip install doc-marshal` or "
    "`uv add --dev doc-marshal`); the hooks pick it up on the next session."
)


def command() -> list[str] | None:
    """The argv prefix that runs the engine, or None when none is installed."""
    for venv in VENV_DIRS:
        for candidate in (
            PROJECT / venv / "bin" / "doc-marshal",
            PROJECT / venv / "Scripts" / "doc-marshal.exe",  # a Windows virtualenv
        ):
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return [str(candidate)]
    on_path = shutil.which("doc-marshal")
    if on_path:
        return [on_path]
    return None


def run(
    *args: str, timeout: int = 25, prefix: list[str] | None = None
) -> subprocess.CompletedProcess[str] | None:
    """Run the engine with `args` from the project directory. None when it could not run. A caller
    that already resolved the engine passes it as `prefix` rather than resolving it twice."""
    prefix = prefix or command()
    if prefix is None:
        return None
    try:
        return subprocess.run(
            [*prefix, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(PROJECT),
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def has_docs_root() -> bool:
    """Whether the project carries a docs-root marker. Cheap on purpose: `git ls-files`, or a
    shallow walk outside git. Only consulted when no engine is installed to ask properly."""
    try:
        listed = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(PROJECT),
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        listed = None
    if listed is not None and listed.returncode == 0:
        return any(Path(entry).name == MARKER for entry in listed.stdout.split("\0") if entry)
    for dirpath, dirnames, filenames in os.walk(PROJECT):
        depth = len(Path(dirpath).relative_to(PROJECT).parts)
        dirnames[:] = [d for d in dirnames if d not in _PRUNE and depth < _MAX_DEPTH]
        if MARKER in filenames:
            return True
    return False
