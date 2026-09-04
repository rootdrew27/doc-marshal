"""`doc-marshal affected`: which notes a code change may have falsified.

The drift spine -- every anchor field whose entries resolve as repo paths -- exists so that "which
docs does this diff touch?" is a question with an answer. This command is that answer. Without it
the rule is only a convention: every note declares its anchor and nobody ever reads it back.

    doc-marshal affected                       # branch commits + uncommitted work
    doc-marshal affected --range main..HEAD    # an explicit range
    doc-marshal affected --paths src/a.py      # paths given directly, no git
    doc-marshal affected --format github       # ::notice:: annotations for CI
    doc-marshal affected --print-range         # just the range, for git log/diff to consume

`--print-range` exists so nothing else has to re-derive the change set by hand: it resolves the
trunk, computes the merge-base and prints `<base>..HEAD`. It prints nothing on the trunk itself.

A note matches when one of its spine entries is, contains, or lies under a changed path, so naming
a directory anchors every file beneath it.

Exit status is 0 whether or not anything matched: an affected note is a prompt to look, not a
failure. `--fail-on-match` inverts that for a pre-merge gate that wants the build to stop.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .config import add_docs_root_option, resolve
from .ontology import Registry
from .paths import (
    anchor_entries,
    changed_paths,
    default_range,
    find_repo_root,
    iter_notes,
    read_note,
    rel_to,
)


def workflow_command(level: str, path: Path, msg: str) -> str:
    """One GitHub Actions workflow command, so a pull request shows the message on the file it
    names. `%` and newlines are what the syntax reserves."""
    return f"::{level} file={path.as_posix()}::{msg.replace('%', '%25').replace(chr(10), '%0A')}"


def matches(ref: str, changed: set[str]) -> list[str]:
    """Changed paths this anchor entry covers.

    Both containment directions count. A ref naming a directory covers everything under it, and a
    ref naming a file inside a deleted or moved directory is still covered when the diff reports
    the directory -- so a note anchored either coarsely or finely surfaces the same way.
    """
    anchor = PurePosixPath(ref.rstrip("/"))
    return sorted(
        path
        for path in changed
        if (candidate := PurePosixPath(path)) == anchor
        or candidate.is_relative_to(anchor)
        or anchor.is_relative_to(candidate)
    )


@dataclass(frozen=True)
class Finding:
    note: Path
    doc_type: str
    hits: list[str]


def find_affected(
    docs_root: Path, registry: Registry, changed: set[str]
) -> tuple[list[Finding], list[str]]:
    """Notes whose spine anchors cover a changed path, and notes whose frontmatter could not be read."""
    findings: list[Finding] = []
    unreadable: list[str] = []
    for note in iter_notes(docs_root, registry.settings):
        meta, _, _, error = read_note(note)
        if error is not None or meta is None:
            unreadable.append(f"{note}: {error}")
            continue
        refs = [ref for field in registry.spine for ref in anchor_entries(meta, field)]
        hits = sorted({hit for ref in refs for hit in matches(ref, changed)})
        if hits:
            doc_type = meta.get("type")
            findings.append(Finding(note, doc_type if isinstance(doc_type, str) else "?", hits))
    return findings, unreadable


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="doc-marshal affected",
        description="Report the notes whose repo-path anchors name code a change touched.",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--range", help="git range, e.g. main..HEAD (default: branch commits plus uncommitted work)"
    )
    source.add_argument("--paths", nargs="+", help="repo-relative paths to match, bypassing git")
    parser.add_argument("--format", choices=("text", "github"), default="text")
    parser.add_argument("--print-range", action="store_true", help="print the resolved git range and exit")
    parser.add_argument("--fail-on-match", action="store_true", help="exit 1 when any note matched")
    add_docs_root_option(parser)
    args = parser.parse_args(argv)

    docs_root, registry = resolve(args.docs_root)
    repo_root = find_repo_root(docs_root)

    if args.print_range:
        resolved = args.range or default_range(repo_root)
        if resolved:
            print(resolved)
        return 0

    if args.paths:
        changed = {PurePosixPath(p).as_posix() for p in args.paths}
    else:
        changed = changed_paths(repo_root, args.range)
    if not changed:
        print("no changed paths -- nothing to match against")
        return 0

    if not registry.spine:
        print(
            "no anchor field resolves as a repo path, so nothing is on the drift spine and no note "
            "can be affected by a code change"
        )
        return 0

    findings, unreadable = find_affected(docs_root, registry, changed)

    if args.format == "github":
        for f in findings:
            print(
                workflow_command(
                    "notice",
                    rel_to(f.note, repo_root),
                    f"anchored to changed code ({', '.join(f.hits)}) -- confirm this {f.doc_type} note is still true",
                )
            )
    else:
        print(f"{len(changed)} changed path(s), {len(findings)} note(s) anchored to them\n")
        for f in findings:
            print(f"{rel_to(f.note, repo_root).as_posix()}  [{f.doc_type}]")
            for hit in f.hits:
                print(f"    <- {hit}")
        if not findings:
            print(
                "no note names any of the changed paths -- either the change is undocumented "
                "or its docs are anchored elsewhere"
            )

    for problem in unreadable:
        print(f"warn:  could not read frontmatter -- {problem}", file=sys.stderr)

    return 1 if (args.fail_on_match and findings) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
