"""Locate the docs root, classify paths under it, read note frontmatter, and ask git what changed.

Every command asks these questions through this module, so none of them can disagree about the
note set or about what a note declares -- a file that is an error in one command and invisible to
another is a gap in the convention, and two frontmatter parsers is the same gap one level down.

Standard library only, deliberately: this runs from a bare interpreter, in CI, on a workstation,
and from a bare checkout with no dependency resolution step.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Iterable
from datetime import date
from pathlib import Path

from .settings import SETTINGS, Settings


class DocMarshalError(Exception):
    """A failure the CLI reports as a message and an exit status, without a traceback."""


# What `classify` returns.
NOTE = "note"  # a note the convention governs
ATTACHMENT = "attachment"  # under the docs root's assets/, exempt from everything
NOT_A_NOTE = "not-a-note"  # generated output, agent-memory, tooling, the marker, non-markdown
FORBIDDEN = "forbidden"  # a file the convention does not allow to exist here


def classify(path: Path, docs_root: Path, settings: Settings = SETTINGS) -> str:
    """Sort a path under the docs root into exactly one kind.

    One function so the validator and the index builder cannot draw the line differently. Order
    matters: `assets/` wins over everything (it is unvalidated at any depth), tooling directories
    win over the forbidden-name check (a README under `.github/` is tooling, not a stray index).
    The marker is not markdown, so it is never a note without a special case.
    """
    if in_assets(path, docs_root, settings):
        return ATTACHMENT
    if path.suffix != ".md":
        return NOT_A_NOTE
    rel = path.relative_to(docs_root) if path.is_relative_to(docs_root) else path
    if settings.excluded_dirs.intersection(rel.parts):
        return NOT_A_NOTE
    if path.name in settings.excluded_names:
        return NOT_A_NOTE
    if path.name in settings.forbidden_names:
        return FORBIDDEN
    return NOTE


def in_assets(path: Path, docs_root: Path, settings: Settings = SETTINGS) -> bool:
    """Whether this path lies inside the docs root's `assets/` directory.

    Positional by design: only the top-level `assets/` is the attachment directory. Attachments
    keep the filename their source gave them -- a third-party document's name is how you re-find
    it and check its revision -- so nothing inside is validated, at any depth.
    """
    if not path.is_relative_to(docs_root):
        return False
    parts = path.relative_to(docs_root).parts
    return len(parts) > 1 and parts[0] == settings.assets_dirname


def is_checkable(path: Path, docs_root: Path, settings: Settings = SETTINGS) -> bool:
    """Whether a validation sweep should report on this path.

    Wider than "is a note": a forbidden file is not a note, but a sweep that skipped it silently
    would let it live in the tree unreported.
    """
    return classify(path, docs_root, settings) in (NOTE, FORBIDDEN)


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


# --- frontmatter --------------------------------------------------------------------------------

# The closing delimiter: `---` alone on its line. Searching for a bare "\n---" instead lets a body
# line like `---nope` close the block, silently truncating the frontmatter after it.
CLOSE_RE = re.compile(r"^---[ \t]*$", re.MULTILINE)

Meta = dict[str, "str | list[str]"]


def split_frontmatter(text: str) -> tuple[str | None, str]:
    """Return (frontmatter_block, body). frontmatter_block is None when absent."""
    if not text.startswith("---\n"):
        return None, text
    close = CLOSE_RE.search(text, 4)
    if close is None:
        return None, text
    return text[4 : close.start()], text[close.end() :]


def _unquote(value: str) -> str:
    """Strip one *matched* pair of surrounding quotes.

    Stripping quote characters unconditionally corrupts any value that merely ends in one:
    `it is not "done"` loses its closing quote and keeps the opening one, and the damage lands
    verbatim in the generated index.
    """
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def parse_frontmatter(block: str) -> Meta:
    """Parse the subset the convention uses: scalar fields and dash-item lists.

    Raises ValueError on anything richer, so an unparseable block fails loudly rather than
    validating as empty. This strictness is the convention, enforced at parse time -- it is why a
    YAML library is not used (SPEC.md section 9).
    """
    result: Meta = {}
    current_list: list[str] | None = None
    for lineno, raw in enumerate(block.splitlines(), start=2):
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        if line.startswith((" ", "\t", "-")):
            item = line.strip()
            if not item.startswith("- "):
                raise ValueError(f"line {lineno}: expected a '- ' list item, got {line!r}")
            if current_list is None:
                raise ValueError(f"line {lineno}: list item with no preceding key")
            current_list.append(_unquote(item[2:].strip()))
            continue
        if ":" not in line:
            raise ValueError(f"line {lineno}: expected 'key: value', got {line!r}")
        key, _, value = line.partition(":")
        key = key.strip()
        if key in result:
            raise ValueError(f"line {lineno}: duplicate key {key!r}")
        value = _unquote(value.strip())
        if value:
            result[key] = value
            current_list = None
        else:
            current_list = []
            result[key] = current_list
    return result


def read_note(path: Path) -> tuple[Meta | None, str, str, str | None]:
    """Read a note as (metadata, body, whole text, error). Exactly one of metadata/error is None.

    The whole text is returned alongside the body so a check that measures the file does not read
    it from disk a second time.
    """
    text = path.read_text(encoding="utf-8")
    block, body = split_frontmatter(text)
    if block is None:
        return None, body, text, "no frontmatter -- every note declares 'type', 'updated', and 'summary'"
    try:
        return parse_frontmatter(block), body, text, None
    except ValueError as exc:
        return None, body, text, f"unparseable frontmatter -- {exc}"


def read_meta(path: Path) -> tuple[Meta | None, str, str | None]:
    """Read a note as (metadata, body, error). Exactly one of metadata/error is None."""
    meta, body, _, error = read_note(path)
    return meta, body, error


# --- the note set -------------------------------------------------------------------------------


def _sorted(paths: Iterable[Path]) -> list[Path]:
    return sorted(paths, key=lambda p: (p.parent.as_posix().lower(), p.name.lower()))


def iter_notes(docs_root: Path, settings: Settings = SETTINGS) -> list[Path]:
    """Every note under the docs root, sorted by folder then filename."""
    return _sorted(p for p in docs_root.rglob("*.md") if classify(p, docs_root, settings) == NOTE)


def iter_named(docs_root: Path, name: str, settings: Settings = SETTINGS) -> list[Path]:
    """Every note under the docs root with this exact filename, sorted.

    For a type the registry pins to one filename: the whole set is findable by name alone, without
    reading frontmatter across the tree to discover which notes claim the type.
    """
    return _sorted(p for p in docs_root.rglob(name) if classify(p, docs_root, settings) == NOTE)


def iter_checkable(docs_root: Path, settings: Settings = SETTINGS) -> list[Path]:
    """Every path a validation sweep should report on -- `is_checkable`, over the whole tree."""
    return _sorted(p for p in docs_root.rglob("*.md") if is_checkable(p, docs_root, settings))


# --- git ----------------------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> str | None:
    """Run a git command, returning its stdout verbatim, or None if the command could not run.

    The output is deliberately not stripped. `git status --porcelain` encodes the status in the
    first two columns, so a leading space is data: stripping it shifts every field of the first
    entry and mangles the path silently. Callers wanting one value use `_git_value`.
    """
    try:
        result = subprocess.run(
            ("git", "-C", str(cwd), *args),
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def _git_value(cwd: Path, *args: str) -> str | None:
    """A git command's output as one stripped value, or None when it failed or said nothing."""
    output = _git(cwd, *args)
    if output is None:
        return None
    return output.strip() or None


def _git_lines(cwd: Path, *args: str) -> list[str] | None:
    """A git command's output as non-empty lines, or None when the command could not run.

    The empty list and None are different answers -- "git says nothing changed" against "git could
    not tell us" -- and callers that collapse them lose the distinction `edited_notes` rests on.
    """
    output = _git(cwd, *args)
    if output is None:
        return None
    return [line for line in output.splitlines() if line]


def git_toplevel(start: Path) -> Path | None:
    toplevel = _git_value(start, "rev-parse", "--show-toplevel")
    return Path(toplevel).resolve() if toplevel else None


# --- the docs root ------------------------------------------------------------------------------

# Directories no marker search descends into. A name-based prune, only for the non-git fallback:
# inside a repository, `git ls-files` already honours .gitignore.
_PRUNE = frozenset({".git", "node_modules", ".venv", "venv", "__pycache__", ".tox", ".nox", "site-packages", ".mypy_cache", ".ruff_cache", ".pytest_cache"})
_MAX_DEPTH = 6

# Names a repository commonly gives its documentation. Consulted only to make the "no marker"
# message useful -- never to pick a docs root (SPEC.md section 4.1.1).
COMMON_DOCS_DIRS = ("docs", "doc", "agent-docs", "notes", "documentation")


def find_markers(
    repo_root: Path, cwd: Path | None = None, settings: Settings = SETTINGS, *, stop_at: Path | None = None
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
    start = (cwd or Path.cwd()).resolve()
    for base in (start, *start.parents):
        if (base / settings.marker_name).is_file():
            found.add((base / settings.marker_name).resolve())
        if base == stop_at:
            break
    listed = _git(repo_root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    if listed is not None:
        for entry in listed.split("\0"):
            if entry and Path(entry).name == settings.marker_name:
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

    cwd = Path.cwd().resolve()
    toplevel = git_toplevel(cwd)
    repo_root = toplevel or cwd
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
    toplevel = git_toplevel(docs_root)
    if toplevel and toplevel != docs_root:
        return toplevel
    superproject = _git_value(docs_root, "rev-parse", "--show-superproject-working-tree")
    if superproject:
        return Path(superproject).resolve()
    return docs_root.parent


# --- the change set a run is scoped to -----------------------------------------------------------
#
# The drift spine exists so that "which docs does this diff touch?" has an answer. Answering it
# needs the diff, so the git plumbing lives here beside the frontmatter reader rather than in the
# one command that happens to need it first -- `check` uses the same helpers to tell an edited note
# from an untouched one.

TRUNK_CANDIDATES = ("main", "master", "trunk", "develop")


def resolve_trunk(repo_root: Path) -> str | None:
    """The trunk ref, resolved rather than assumed.

    `origin/HEAD` is the authoritative answer when the remote published one. Falling back to a
    local branch name is a guess, so it is ordered and only ever names a branch that exists.
    """
    head = _git_value(repo_root, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    if head:
        return head
    refs = _git_value(
        repo_root,
        "for-each-ref",
        "--format=%(refname:short)",
        *(f"refs/heads/{name}" for name in TRUNK_CANDIDATES),
    )
    return refs.splitlines()[0] if refs else None


def default_range(repo_root: Path) -> str | None:
    """`<merge-base>..HEAD` against the trunk, or None on the trunk itself or outside a repo.

    Three dots are avoided by computing the base explicitly: two-dot `trunk..HEAD` would show
    anything merged into the trunk since the branch point, reversed.
    """
    trunk = resolve_trunk(repo_root)
    if not trunk:
        return None
    base = _git_value(repo_root, "merge-base", trunk, "HEAD")
    head = _git_value(repo_root, "rev-parse", "HEAD")
    if not base or base == head:
        return None
    return f"{base}..HEAD"


def _porcelain_paths(repo_root: Path, pathspec: Path | None = None) -> set[str] | None:
    """Paths differing from HEAD in the working tree, staged or not, including untracked.

    None when git could not answer. An empty set means the tree is clean, which is a different
    fact -- and the one a fresh CI checkout always reports.

    `pathspec` bounds the walk. Unbounded, `--untracked-files=all` stats every file in the repo,
    which is wasted work for a caller that only asks about the docs tree.
    """
    scope = ("--", str(pathspec)) if pathspec is not None else ()
    status = _git(repo_root, "status", "--porcelain", "-z", "--untracked-files=all", *scope)
    if status is None:
        return None
    paths: set[str] = set()
    fields = status.split("\0")
    index = 0
    while index < len(fields):
        entry = fields[index]
        index += 1
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        if "R" in code or "C" in code:  # rename/copy: the source follows as its own field
            if index < len(fields):
                paths.add(fields[index])
                index += 1
        paths.add(path)
    return paths


def changed_paths(repo_root: Path, rev_range: str | None = None) -> set[str]:
    """Repo-relative paths a change touched.

    With an explicit range, exactly that range. Without one, the branch's own commits plus
    uncommitted work -- which is what a docs run is actually scoped to, since the code being
    documented is routinely still in the working tree.
    """
    paths: set[str] = set()
    if rev_range is None:
        paths |= _porcelain_paths(repo_root) or set()
    effective = rev_range if rev_range is not None else default_range(repo_root)
    if effective:
        paths |= set(_git_lines(repo_root, "diff", "--name-only", effective) or ())
    return paths


def edited_notes(
    repo_root: Path, rev_range: str | None = None, pathspec: Path | None = None
) -> set[Path] | None:
    """Absolute paths of notes the change touched, or None when git cannot say.

    Without a range this is the working tree, which is what a workstation run means by "edited".
    CI cannot use that answer: a fresh checkout's tree is always clean, so the working-tree reading
    there is an empty set that looks like "nothing edited" and quietly disables every check built
    on it. Given a range, that range is the change instead.

    None and the empty set mean different things -- "cannot tell" versus "nothing edited" -- so
    checks that only apply to an edited file stay silent rather than guess.
    """
    paths = (
        _git_lines(repo_root, "diff", "--name-only", rev_range)
        if rev_range
        else _porcelain_paths(repo_root, pathspec)
    )
    if paths is None:
        return None
    return {(repo_root / p).resolve() for p in paths}


def change_start(repo_root: Path, rev_range: str | None = None) -> date | None:
    """The day the change began: today for the working tree, else the author date of the range's
    earliest commit. None when git cannot say.

    This is the bar an edited note's `updated` is held to. Comparing against today instead would
    fail every note dated the day it was edited once its pull request is a day old -- and author
    dates rather than committer dates, so a rebase before merge does not move the bar either.
    """
    if not rev_range:
        return date.today()
    lines = _git_lines(repo_root, "log", "--format=%as", "--reverse", rev_range)
    if not lines:
        return None
    try:
        return date.fromisoformat(lines[0].strip())
    except ValueError:
        return None
