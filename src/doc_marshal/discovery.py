"""Locate the docs root: `--docs-root`, the environment, then the marker. Never by name."""

from __future__ import annotations

import os
from pathlib import Path

from .errors import DocMarshalError
from .git import Git, toplevel
from .paths import rel_to
from .settings import SETTINGS, Settings

# Directories no marker search descends into. A name-based prune, only for the non-git fallback:
# inside a repository, `git ls-files` already honours .gitignore.
_PRUNE = frozenset(
    {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".tox",
        ".nox",
        "site-packages",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
    }
)
_MAX_DEPTH = 6

# Names a repository commonly gives its documentation. Consulted only to make the "no marker"
# message useful -- never to pick a docs root (SPEC.md section 4.1.1).
COMMON_DOCS_DIRS = ("docs", "doc", "agent-docs", "notes", "documentation")


def find_markers(
    repo_root: Path, cwd: Path, settings: Settings = SETTINGS, *, stop_at: Path | None = None
) -> list[Path]:
    """Every marker file in the repository, sorted.

    Inside a git repository the search is `git ls-files` over tracked and untracked files, which
    respects .gitignore and costs nothing in a large tree. Outside one it is a bounded walk. Either
    way the ancestors of the working directory are checked first, so a command run from inside the
    docs root finds its marker without any search at all. The ancestor walk ends at `stop_at` --
    the git toplevel -- and, when there is none, at the filesystem root: outside git the working
    directory is nothing more than where the command happened to run, and a marker above it is
    still the marker.
    """
    found: set[Path] = set()
    start = cwd.resolve()
    for base in (start, *start.parents):
        if (base / settings.marker_name).is_file():
            found.add((base / settings.marker_name).resolve())
        if base == stop_at:
            break
    listed = Git(repo_root).listed()
    if listed is not None:
        for entry in listed:
            if Path(entry).name == settings.marker_name:
                candidate = (repo_root / entry).resolve()
                if candidate.is_file():
                    found.add(candidate)
    else:
        for dirpath, dirnames, filenames in os.walk(repo_root):
            depth = len(Path(dirpath).relative_to(repo_root).parts)
            dirnames[:] = [d for d in dirnames if d not in _PRUNE and depth < _MAX_DEPTH]
            if settings.marker_name in filenames:
                found.add((Path(dirpath) / settings.marker_name).resolve())
    return sorted(found)


def cwd_repo(cwd: Path | None = None) -> tuple[Path, Path, Path | None]:
    """The working directory, the repository it is in, and the git toplevel when there is one.
    Outside git the working directory stands in for the repository. `cwd` defaults to the
    process's, and is a parameter so a test can name one instead."""
    cwd = (cwd or Path.cwd()).resolve()
    root = toplevel(cwd)
    return cwd, root or cwd, root


def find_docs_root(explicit: str | None = None, settings: Settings = SETTINGS) -> Path:
    """Resolve the docs root: `--docs-root`, then the environment, then the marker. Never by name.

    Raises `DocMarshalError` rather than guessing: a command that picked a `docs/` because it was
    called that would walk into a Sphinx tree and report several hundred errors on files that were
    never notes.
    """
    for label, override in (("--docs-root", explicit), (settings.env_var, os.environ.get(settings.env_var))):
        if override:
            root = Path(override).expanduser().resolve()
            if not root.is_dir():
                raise DocMarshalError(f"{label} is not a directory: {root}")
            return root

    cwd, repo_root, toplevel = cwd_repo()
    markers = find_markers(repo_root, cwd, settings, stop_at=toplevel)
    if len(markers) == 1:
        return markers[0].parent
    if markers:
        listing = "\n".join(f"  {rel_to(m.parent, repo_root)}/" for m in markers)
        raise DocMarshalError(
            f"{len(markers)} {settings.marker_name} markers found, and one repository has one docs "
            f"root:\n{listing}\nRemove all but one, or pass --docs-root to choose for this run."
        )

    considered = [d for d in COMMON_DOCS_DIRS if (repo_root / d).is_dir()]
    hint = (
        "Directories considered, none carrying a marker: " + ", ".join(f"{d}/" for d in considered)
        if considered
        else "No directory under it looks like a docs tree."
    )
    raise DocMarshalError(
        f"no {settings.marker_name} marker found under {repo_root}. {hint}\n"
        f"Run `doc-marshal init [path]` to mark the docs root (default: {settings.default_docs_dir}/), "
        f"or pass --docs-root PATH / set ${settings.env_var}."
    )


def find_repo_root(docs_root: Path) -> Path:
    """The root that `repo-path` anchors are relative to.

    The docs root's own git toplevel is the answer whenever it is a distinct directory: the docs
    live inside the code repo, and that repo staying a submodule of some larger hub must not widen
    the root (paths are written from the code repo, not the hub). The superproject is consulted only
    in the layout it exists for -- the docs being their own repo mounted as a submodule, where the
    toplevel IS the docs root and resolves nothing.
    """
    root = toplevel(docs_root)
    if root and root != docs_root:
        return root
    superproject = Git(docs_root).superproject()
    if superproject:
        return superproject
    return docs_root.parent
