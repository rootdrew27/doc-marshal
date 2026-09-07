"""What git knows about the repository, behind one object a run asks and a test can answer for.

`Git` is the port: its public methods are every question the package puts to git -- which files
are tracked, what a change touched, when it began, whether a `--range` is one git would read as
the caller means. Each command builds one for the repository it runs in and hands it on (through
`Scope` to the rules, as an argument elsewhere), so a run asks once and a fake can stand in.
There is deliberately no `Protocol` yet: with one implementation the class itself is the
interface, and a fake subclasses it. Add the protocol the day a second implementation exists.

Every method returns None when git could not answer. None and the empty answer are different
facts -- "cannot tell" against "nothing changed" -- and callers keep them apart (see
`edited_notes`). `toplevel` is the bootstrap: the one question asked of a directory before any
repository is known, to find the root a `Git` is then built on.

Standard library only, deliberately: this runs from a bare interpreter, in CI, on a workstation,
and from a bare checkout with no dependency resolution step.

The drift spine exists so that "which docs does this diff touch?" has an answer. Answering it
needs the diff, so the git plumbing lives here rather than in the one command that happens to
need it first -- `check` uses the same object to tell an edited note from an untouched one.
"""

from __future__ import annotations

import subprocess
from datetime import date
from functools import cached_property
from pathlib import Path, PurePosixPath

from .errors import DocMarshalError

TRUNK_CANDIDATES = ("main", "master", "trunk", "develop")

# Per repository: the tracked files, and every directory that holds one. Both are sets so a
# directory anchor is answered by one lookup rather than a scan of the listing per entry.
Tracked = tuple[frozenset[str], frozenset[str]]


def _pathspec(pathspec: Path | None) -> tuple[str, ...]:
    """The trailing `-- <path>` that bounds a git query, or nothing when the query is unbounded."""
    return ("--", str(pathspec)) if pathspec is not None else ()


def toplevel(start: Path) -> Path | None:
    """`git rev-parse --show-toplevel` from `start`, or None outside a repository -- discovery's
    one question about a directory that may not be one, asked before any `Git` exists."""
    found = Git(start)._value("rev-parse", "--show-toplevel")
    return Path(found).resolve() if found else None


class Git:
    """One repository's git, asked through subprocess."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root

    # --- the one subprocess call, and its readings ------------------------------------------------

    def _run(self, *args: str) -> str | None:
        """Run a git command here, returning its stdout verbatim, or None if it could not run.

        The output is deliberately not stripped. `git status --porcelain` encodes the status in
        the first two columns, so a leading space is data: stripping it shifts every field of the
        first entry and mangles the path silently. Callers wanting one value use `_value`.
        """
        try:
            result = subprocess.run(
                ("git", "-C", str(self.repo_root), *args),
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return result.stdout if result.returncode == 0 else None

    def _value(self, *args: str) -> str | None:
        """A git command's output as one stripped value, or None when it failed or said nothing."""
        output = self._run(*args)
        if output is None:
            return None
        return output.strip() or None

    def _lines(self, *args: str) -> list[str] | None:
        """A git command's output as non-empty lines, or None when the command could not run.

        The empty list and None are different answers -- "git says nothing changed" against "git
        could not tell us" -- and callers that collapse them lose the distinction `edited_notes`
        rests on.
        """
        output = self._run(*args)
        if output is None:
            return None
        return [line for line in output.splitlines() if line]

    def _entries(self, *args: str) -> list[str] | None:
        """A `-z` git command's output as its NUL-separated entries, or None when the command
        could not run. The NUL sibling of `_lines`, with the same None-versus-empty contract."""
        output = self._run(*args)
        if output is None:
            return None
        return [entry for entry in output.split("\0") if entry]

    # --- the port ---------------------------------------------------------------------------------

    def superproject(self) -> Path | None:
        """The superproject's working tree when this repository is a submodule, else None."""
        found = self._value("rev-parse", "--show-superproject-working-tree")
        return Path(found).resolve() if found else None

    def listed(self) -> list[str] | None:
        """Every tracked and untracked-but-not-ignored path, relative to the root, or None outside
        a repository. What a marker search walks instead of the filesystem."""
        return self._entries("ls-files", "-z", "--cached", "--others", "--exclude-standard")

    @cached_property
    def _tracked(self) -> Tracked | None:
        """`git ls-files`, read once per `Git`; None outside a repository is cached too."""
        entries = self._entries("ls-files", "-z")
        if entries is None:
            return None
        holders = {str(parent) for entry in entries for parent in PurePosixPath(entry).parents}
        return frozenset(entries), frozenset(holders - {"."})

    def is_tracked(self, target: Path) -> bool | None:
        """Whether git tracks `target` -- a file by name, a directory by anything under it -- or
        None outside a git repository.

        An anchor that exists on disk but is not committed passes in the one checkout that has it
        and fails in every other and in CI, which is precisely the local-versus-CI disagreement
        the tool exists to remove.
        """
        if self._tracked is None:
            return None
        files, dirs = self._tracked
        rel = target.relative_to(self.repo_root).as_posix()
        return rel in files or rel in dirs

    def validate_range(self, rev_range: str) -> None:
        """Refuse a `--range` that git would silently read as something else.

        The form is `A..B`, both ends commits, `A` an ancestor of `B`. A single ref, a three-dot
        range, a reversed pair or a base a shallow clone cannot resolve all used to pass with exit
        0 and quietly disable the freshness and lead checks. Each failure names the part at fault.
        """
        base, dots, head = rev_range.partition("..")
        if not dots or not base or not head or head.startswith("."):
            raise DocMarshalError(f"--range must be A..B, two commits and two dots: {rev_range!r}")
        for name in (base, head):
            if self._run("rev-parse", "--verify", "--quiet", f"{name}^{{commit}}") is None:
                raise DocMarshalError(
                    f"--range names {name!r}, which is not a commit here (shallow clone?): {rev_range}"
                )
        if self._run("merge-base", "--is-ancestor", base, head) is None:
            raise DocMarshalError(f"--range {rev_range}: {base!r} is not an ancestor of {head!r}")

    def resolve_trunk(self) -> str | None:
        """The trunk ref, resolved rather than assumed.

        `origin/HEAD` is the authoritative answer when the remote published one. Falling back to
        a local branch name is a guess, so it is ordered and only ever names a branch that exists.
        """
        head = self._value("symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
        if head:
            return head
        refs = self._value(
            "for-each-ref",
            "--format=%(refname:short)",
            *(f"refs/heads/{name}" for name in TRUNK_CANDIDATES),
        )
        return refs.splitlines()[0] if refs else None

    def default_range(self) -> str | None:
        """`<merge-base>..HEAD` against the trunk, or None on the trunk itself or outside a repo.

        Three dots are avoided by computing the base explicitly: two-dot `trunk..HEAD` would show
        anything merged into the trunk since the branch point, reversed.
        """
        trunk = self.resolve_trunk()
        if not trunk:
            return None
        base = self._value("merge-base", trunk, "HEAD")
        head = self._value("rev-parse", "HEAD")
        if not base or base == head:
            return None
        return f"{base}..HEAD"

    def _porcelain_paths(self) -> set[str] | None:
        """Paths differing from HEAD in the working tree, staged or not, including untracked.

        None when git could not answer. An empty set means the tree is clean, which is a
        different fact -- and the one a fresh CI checkout always reports.
        """
        status = self._run("status", "--porcelain", "-z", "--untracked-files=all")
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
            # rename/copy: the source follows as its own field
            if ("R" in code or "C" in code) and index < len(fields):
                paths.add(fields[index])
                index += 1
            paths.add(path)
        return paths

    def changed_paths(self, rev_range: str | None = None) -> set[str]:
        """Repo-relative paths a change touched.

        With an explicit range, exactly that range. Without one, the branch's own commits plus
        uncommitted work -- which is what a docs run is actually scoped to, since the code being
        documented is routinely still in the working tree.
        """
        paths: set[str] = set()
        if rev_range is None:
            paths |= self._porcelain_paths() or set()
        effective = rev_range if rev_range is not None else self.default_range()
        if effective:
            paths |= set(self._lines("diff", "--name-only", effective) or ())
        return paths

    def _content_changes(self, rev_range: str | None, pathspec: Path | None) -> set[str] | None:
        """Paths whose content differs across the change, a pure `git mv` excluded.

        `--find-renames=100%` reports an exact rename as one `R100` line and nothing else; a
        rename with an edit is a delete and an add, and the add counts. Without a range the
        comparison is the working tree against HEAD, staged or not.
        """
        lines = self._lines("diff", "--name-status", "--find-renames=100%", rev_range or "HEAD", *_pathspec(pathspec))
        if lines is None:
            return None
        changed: set[str] = set()
        for line in lines:
            status, *names = line.split("\t")
            if not status.startswith("R"):
                changed.update(names)
        return changed

    def edited_notes(self, rev_range: str | None = None, pathspec: Path | None = None) -> set[Path] | None:
        """Absolute paths of notes the change touched, or None when git cannot say.

        Without a range this is the working tree, which is what a workstation run means by
        "edited". CI cannot use that answer: a fresh checkout's tree is always clean, so the
        working-tree reading there is an empty set that looks like "nothing edited" and quietly
        disables every check built on it. Given a range, that range is the change instead.

        A `git mv` with no content change is not an edit: nothing in the note became stale. A
        plain `mv` is a delete plus an untracked file, and the untracked file counts as new.

        None and the empty set mean different things -- "cannot tell" versus "nothing edited" --
        so checks that only apply to an edited file stay silent rather than guess.
        """
        paths = self._content_changes(rev_range, pathspec)
        if paths is None:
            return None
        if rev_range is None:
            untracked = self._entries("ls-files", "-z", "--others", "--exclude-standard", *_pathspec(pathspec))
            paths.update(untracked or ())
        return {(self.repo_root / p).resolve() for p in paths}

    def change_start(self, rev_range: str | None = None) -> date | None:
        """The day the change began: today for the working tree, else the author date of the
        range's earliest commit. None when git cannot say.

        This is the bar an edited note's `updated` is held to. Comparing against today instead
        would fail every note dated the day it was edited once its pull request is a day old --
        and author dates rather than committer dates, so a rebase before merge does not move the
        bar either.
        """
        if not rev_range:
            return date.today()
        lines = self._lines("log", "--format=%as", "--reverse", rev_range)
        if not lines:
            return None
        try:
            return date.fromisoformat(lines[0].strip())
        except ValueError:
            return None
