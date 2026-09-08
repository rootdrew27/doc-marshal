"""`doc-marshal check`: validate notes against the effective profile.

Checks the files named on the command line: a run fixes the docs it touched, not every doc under
the docs tree. `--all` is the sweep CI runs.

    doc-marshal check docs/ledger/schema.md docs/decisions/0004-parking.md
    doc-marshal check --all --range main..HEAD

Exits 1 if any error is reported. Warnings never fail the run. The policies themselves live in
`policies`, as one ordered pipeline; this module sorts the targets, builds the scope a run shares,
reads each note once and runs the pipeline over it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import add_docs_tree_option, load_profile
from .discovery import find_docs_tree, find_repo_root
from .errors import DocMarshalError
from .git import Git
from .index import plural
from .note import Note
from .ontology import Profile
from .paths import FORBIDDEN, classify, is_checkable, iter_checkable
from .policies import NOTE_POLICIES, TREE_POLICIES, Scope
from .report import Report
from .settings import Settings
from .vocabulary import build_vocabulary


def unchecked_reason(path: Path, docs_tree: Path, settings: Settings) -> str | None:
    """Why a named path is nothing the validator governs, or None when it is a note to check.

    A hook handed every file a change touched asks to skip these; anyone else naming one is told,
    because a run that checked nothing and reported clean is the worst answer it could give.
    """
    if not path.is_file():
        return "not a file"
    if not path.is_relative_to(docs_tree):
        return f"outside the docs tree ({docs_tree}) -- wrong --docs-tree?"
    if not is_checkable(path, docs_tree, settings):
        return (
            f"not a note ({classify(path, docs_tree, settings)}) -- generated, agent-memory, "
            "tooling and asset files are never validated"
        )
    return None


def run(
    docs_tree: Path,
    profile: Profile,
    targets: list[Path],
    *,
    sweep: bool,
    rev_range: str | None = None,
    skip_non_notes: bool = False,
) -> tuple[Report, int]:
    """Validate `targets` (or the whole tree with `sweep`). Returns the report and the count checked."""
    settings = profile.settings
    repo_root = find_repo_root(docs_tree)
    git = Git(repo_root)
    if rev_range:
        git.validate_range(rev_range)
    report = Report(root=repo_root)

    to_check: list[Path] = []
    for path in targets:
        why = unchecked_reason(path, docs_tree, settings)
        if why is None:
            to_check.append(path)
        elif not skip_non_notes:
            report.error(path, why)

    # Everything git and the tree are asked is asked after the targets are sorted, so a hook
    # handed a markdown file that is not a note pays for nothing.
    scope = Scope(docs_tree, profile, git, rev_range, in_scope=None if sweep else set(targets))
    if to_check:
        scope.vocabulary = build_vocabulary(docs_tree, profile, report, to_check, sweep)
    for path in to_check:
        if classify(path, docs_tree, settings) == FORBIDDEN:
            report.error(
                path, f"{path.name} does not belong under {docs_tree.name}/ -- {settings.forbidden_reason(path)}"
            )
            continue
        note = Note.read(path, profile)
        for policy in NOTE_POLICIES:
            policy(note, scope, report)

    for tree_policy in TREE_POLICIES:
        tree_policy(scope, report)
    return report, len(to_check)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="doc-marshal check",
        description="Validate notes against the effective profile. Exits 1 on any error; warnings never fail.",
    )
    parser.add_argument("paths", nargs="*", type=Path, help="notes to check")
    parser.add_argument("--all", action="store_true", help="sweep every note under the docs tree (what CI runs)")
    parser.add_argument(
        "--range",
        help="git range whose notes count as edited, e.g. main..HEAD (default: the working tree; "
        "CI has no working-tree changes and must pass this to check freshness at all)",
    )
    parser.add_argument(
        "--skip-non-notes",
        action="store_true",
        help="silently skip paths that are not notes under the docs tree, and exit 0 when there is "
        "no docs tree at all -- for hooks handed every file a change touched",
    )
    parser.add_argument(
        "--format",
        choices=("text", "github"),
        default="text",
        help="github: one workflow command per finding, so a pull request shows it on the file",
    )
    add_docs_tree_option(parser)
    args = parser.parse_args(argv)

    if not args.all and not args.paths:
        parser.error("name the notes to check, or pass --all")

    try:
        docs_tree = find_docs_tree(args.docs_tree)
    except DocMarshalError:
        if args.skip_non_notes:
            return 0
        raise
    profile = load_profile(docs_tree)

    targets = iter_checkable(docs_tree, profile.settings) if args.all else [p.resolve() for p in args.paths]
    report, checked = run(
        docs_tree,
        profile,
        targets,
        sweep=args.all,
        rev_range=args.range,
        skip_non_notes=args.skip_non_notes,
    )

    for line in report.annotations() if args.format == "github" else report.lines():
        print(line)
    errors, warnings = report.count("error"), report.count("warning")
    if checked or not args.skip_non_notes:
        print(f"\n{checked} {plural(checked)} checked -- {errors} error(s), {warnings} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
