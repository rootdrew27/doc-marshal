"""Whether an anchor entry resolves by its field's kinds.

An anchor field's `resolves` says what its entries may be -- URLs, paths under the docs root,
paths anywhere in the repository, or opaque values -- and this module is the one reading of what
each kind accepts. `check` calls it for every anchor field a note carries.
"""

from __future__ import annotations

from pathlib import Path

from .ontology import AnchorField, Registry
from .paths import exists_exact, is_absolute_entry, is_tracked, is_url, rel_to
from .report import Report

_KIND_ORDER = ("url", "docs-path", "repo-path", "opaque")


def describe_anchor(anchor: AnchorField, docs_root: Path, repo_root: Path) -> str:
    """What the field's entries may be, as prose for a message."""
    docs_prefix = rel_to(docs_root, repo_root)
    words = {
        "url": "URLs",
        "docs-path": f"repo-relative paths under {docs_prefix}/",
        "repo-path": "repo-relative paths",
        "opaque": "non-empty values",
    }
    return " or ".join(words[k] for k in _KIND_ORDER if k in anchor.resolves)


def resolve_entry(entry: str, anchor: AnchorField, docs_root: Path, repo_root: Path, registry: Registry) -> str | None:
    """Why this entry fails the field's `resolves` kinds, or None when some kind accepts it.

    Every path in frontmatter is written from the repo root, never from the docs root and never
    absolute -- one path convention for every field. A `docs-path` that resolves outside the docs
    root is rejected on purpose: code belongs in a `repo-path` field, and accepting it here would
    let a note satisfy its anchor while staying off the drift spine.

    A path must name something strictly inside the repository. `.` and its spellings resolve to
    the root, which exists, and a note "anchored" to the whole repository is anchored to nothing
    -- every change would touch it. A directory inside the repository is fine: a spec about a
    package anchors to the package. Existence is checked with exact spelling (`exists_exact`), so
    a case-insensitive filesystem cannot pass a path that CI will fail; and "spelled exactly"
    admits no `.` or `..` segment, since the resolver and `affected` would otherwise agree on a
    file the text does not name.

    A path must also be tracked by git. A file that exists only in this checkout satisfies the
    anchor here and nowhere else -- six of one project's notes anchored to an uncommitted config
    file and passed for months -- so existence on disk is not the question; presence in
    `git ls-files` is. That holds for either path kind and needs a repository to answer.
    """
    kinds = anchor.resolves
    name = anchor.name
    if "opaque" in kinds and entry.strip():
        return None
    if "url" in kinds and is_url(entry):
        return None
    if "docs-path" not in kinds and "repo-path" not in kinds:
        return f"{name} must be an http(s) URL: {entry}"
    if is_absolute_entry(entry):
        return f"{name} must be repo-relative, not absolute: {entry}"
    # Split by hand: a path object collapses `.` segments before they can be seen.
    if any(part in (".", "..") for part in entry.split("/")):
        return f"{name} must be spelled exactly, from the repo root, with no . or .. segments: {entry}"
    resolved = (repo_root / entry).resolve()
    if resolved == repo_root or not resolved.is_relative_to(repo_root):
        return f"{name} must name a path inside the repository, not the root itself: {entry!r}"
    found = exists_exact(repo_root, resolved) and ("repo-path" in kinds or resolved.is_relative_to(docs_root))
    if found:
        tracked = is_tracked(repo_root, resolved)
        if tracked is None:
            return f"{name} needs a git repository to confirm the path is tracked: {entry}"
        if not tracked:
            return (
                f"{name} path exists but git does not track it, so it resolves in this checkout "
                f"only -- commit it, or describe it in prose rather than anchoring to it: {entry}"
            )
        return None
    if "repo-path" in kinds:
        return f"{name} path does not exist (spelled exactly, from the repo root): {entry}"
    if not resolved.is_relative_to(docs_root):
        docs_prefix = rel_to(docs_root, repo_root)
        spine = " or ".join(registry.spine) or "a repo-path field"
        url_part = "a URL or " if "url" in kinds else ""
        return (
            f"{name} must be {url_part}a path under {docs_prefix}/ -- written from the repo root, "
            f"and code paths belong in {spine} instead: {entry}"
        )
    return f"{name} path does not exist (spelled exactly, from the repo root): {entry}"


def check_anchor(
    path: Path,
    anchor: AnchorField,
    entries: object,
    docs_root: Path,
    repo_root: Path,
    registry: Registry,
    report: Report,
) -> None:
    """A declared anchor field, whenever present, is a list whose every entry resolves by its kind."""
    if not isinstance(entries, list):
        report.error(path, f"'{anchor.name}' must be a list of {describe_anchor(anchor, docs_root, repo_root)}")
        return
    for entry in entries:
        problem = resolve_entry(entry, anchor, docs_root, repo_root, registry)
        if problem is not None:
            report.error(path, problem)
