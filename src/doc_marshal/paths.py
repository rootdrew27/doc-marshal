"""Classify paths under the docs tree and enumerate the note set.

Every command asks these questions through this module, so none of them can disagree about the
note set -- a file that is an error in one command and invisible to another is a gap in the
convention.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from .settings import MARKDOWN_SUFFIXES, NOTE_SUFFIX, SETTINGS, Settings

# What `classify` returns.
NOTE = "note"  # a note the convention governs
ASSET = "asset"  # under the docs tree's assets/, exempt from everything
NOT_A_NOTE = "not-a-note"  # generated output, agent-memory, tooling, the config, non-markdown
FORBIDDEN = "forbidden"  # a file the convention does not allow to exist here


def classify(path: Path, docs_tree: Path, settings: Settings = SETTINGS) -> str:
    """Sort a path under the docs tree into exactly one kind.

    One function so the validator and the index builder cannot draw the line differently. Order
    matters: `assets/` wins over everything (it is unvalidated at any depth), tooling directories
    win over the forbidden-name check (a README under `.github/` is tooling, not a stray index).
    The config is not markdown, so it is never a note without a special case.

    Names are judged case-insensitively, because the filesystems this runs on disagree about
    case and a `Readme.md` is the same stray index as a `README.md`. A markdown file under any
    other spelling of the suffix is forbidden rather than ignored: silently skipping `.MD` left a
    note nobody validated. The generated index is a non-note only at the top of the docs tree, spelled
    exactly; anywhere else, or in any other case, it is a second index and forbidden.
    """
    if in_assets(path, docs_tree, settings):
        return ASSET
    if path.suffix.lower() not in MARKDOWN_SUFFIXES:
        return NOT_A_NOTE
    if settings.excluded_dirs.intersection(rel_to(path, docs_tree).parts):
        return NOT_A_NOTE
    if path.name == settings.index_name and path.parent == docs_tree:
        return NOT_A_NOTE
    if path.name in settings.memory_names:
        return NOT_A_NOTE
    if settings.forbidden_reason(path) is not None:
        return FORBIDDEN
    return NOTE


def in_assets(path: Path, docs_tree: Path, settings: Settings = SETTINGS) -> bool:
    """Whether this path lies inside the docs tree's `assets/` directory.

    Positional by design: only the top-level `assets/` is the asset directory. Assets
    keep the filename their source gave them -- a third-party document's name is how you re-find
    it and check its revision -- so nothing inside is validated, at any depth.
    """
    if not path.is_relative_to(docs_tree):
        return False
    parts = path.relative_to(docs_tree).parts
    return len(parts) > 1 and parts[0] == settings.assets_dirname


def is_checkable(path: Path, docs_tree: Path, settings: Settings = SETTINGS) -> bool:
    """Whether a validation sweep should report on this path.

    Wider than "is a note": a forbidden file is not a note, but a sweep that skipped it silently
    would let it live in the tree unreported.
    """
    return classify(path, docs_tree, settings) in (NOTE, FORBIDDEN)


def rel_to(path: Path, root: Path) -> Path:
    """`path` relative to `root`, or unchanged when it lies outside -- for readable messages."""
    return path.relative_to(root) if path.is_relative_to(root) else path


_LISTINGS: dict[Path, frozenset[str]] = {}


def exists_exact(root: Path, target: Path) -> bool:
    """Whether `target`, a resolved path, exists under `root` spelled exactly as given.

    `Path.exists()` is the filesystem's opinion, and on a case-insensitive one (APFS, NTFS) it
    accepts `Src/Ledger.py` for `src/ledger.py`. A note that passes there fails on Linux CI, which
    is the one disagreement between a local run and CI this tool exists to remove. So each
    component is looked up in a real directory listing instead, and the listings are cached for
    the life of the process -- every command is one short-lived process, so nothing invalidates.

    A path outside `root`, or `root` itself, does not exist for this purpose: nothing in the
    repository can anchor to or link at something the repository does not contain.
    """
    if target == root or not target.is_relative_to(root):
        return False
    current = root
    for part in target.relative_to(root).parts:
        names = _LISTINGS.get(current)
        if names is None:
            try:
                names = _LISTINGS[current] = frozenset(os.listdir(current))
            except OSError:
                return False
        if part not in names:
            return False
        current = current / part
    return True


def _sorted(paths: Iterable[Path]) -> list[Path]:
    return sorted(paths, key=lambda p: (p.parent.as_posix().lower(), p.name.lower()))


def iter_notes(docs_tree: Path, settings: Settings = SETTINGS) -> list[Path]:
    """Every note under the docs tree, sorted by folder then filename."""
    return _sorted(p for p in docs_tree.rglob(f"*{NOTE_SUFFIX}") if classify(p, docs_tree, settings) == NOTE)


def iter_checkable(docs_tree: Path, settings: Settings = SETTINGS) -> list[Path]:
    """Every path a validation sweep should report on -- `is_checkable`, over the whole tree,
    including the markdown files whose suffix is misspelled and therefore forbidden."""
    # The suffix is read before the file is stat'd, so an asset-heavy tree costs one string
    # test per non-markdown entry rather than one syscall.
    return _sorted(
        p
        for p in docs_tree.rglob("*")
        if p.suffix.lower() in MARKDOWN_SUFFIXES and p.is_file() and is_checkable(p, docs_tree, settings)
    )


def is_url(entry: str) -> bool:
    """Whether an anchor entry is a web address rather than a path. The one reading, so the
    validator and `drifted` agree about which entries the diff is matched against."""
    return urlparse(entry).scheme in ("http", "https")


def is_absolute_entry(entry: str) -> bool:
    """Whether a path entry is absolute under either the POSIX or the host spelling. Anchors and
    `--paths` are written from the repo root, so an absolute one matches nothing."""
    return PurePosixPath(entry).is_absolute() or Path(entry).is_absolute()
