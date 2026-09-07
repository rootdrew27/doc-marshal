"""`doc-marshal check`: validate notes against the registry.

Checks the files named on the command line: a run fixes the docs it touched, not every doc under
the docs root. `--all` is the sweep CI runs.

    doc-marshal check docs/ledger/schema.md docs/decisions/0004-parking.md
    doc-marshal check --all --range main..HEAD

Exits 1 if any error is reported. Warnings never fail the run. The rules themselves live in
`rules`, as one ordered pipeline; this module sorts the targets, builds the scope a run shares,
reads each note once and runs the pipeline over it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import add_docs_root_option, load_registry
from .discovery import find_docs_root, find_repo_root
from .errors import DocMarshalError
from .git import Git
from .index import plural
from .note import Note
from .ontology import Registry
from .paths import FORBIDDEN, classify, is_checkable, iter_checkable
from .report import Report
from .rules import NOTE_RULES, TREE_RULES, Scope
from .settings import Settings
from .vocabulary import build_vocabulary


def unchecked_reason(path: Path, docs_root: Path, settings: Settings) -> str | None:
    """Why a named path is nothing the validator governs, or None when it is a note to check.

    A hook handed every file a change touched asks to skip these; anyone else naming one is told,
    because a run that checked nothing and reported clean is the worst answer it could give.
    """
    if not path.is_file():
        return "not a file"
    if not path.is_relative_to(docs_root):
        return f"outside the docs root ({docs_root}) -- wrong --docs-root?"
    if not is_checkable(path, docs_root, settings):
        return (
            f"not a note ({classify(path, docs_root, settings)}) -- generated, agent-memory, "
            "tooling and attachment files are never validated"
        )
    return None


def run(
    docs_root: Path,
    registry: Registry,
    targets: list[Path],
    *,
    sweep: bool,
    rev_range: str | None = None,
    skip_non_notes: bool = False,
) -> tuple[Report, int]:
    """Validate `targets` (or the whole tree with `sweep`). Returns the report and the count checked."""
    settings = registry.settings
    repo_root = find_repo_root(docs_root)
    git = Git(repo_root)
    if rev_range:
        git.validate_range(rev_range)
    report = Report(root=repo_root)

    to_check: list[Path] = []
    for path in targets:
        why = unchecked_reason(path, docs_root, settings)
        if why is None:
            to_check.append(path)
        elif not skip_non_notes:
            report.error(path, why)

    # Everything git and the tree are asked is asked after the targets are sorted, so a hook
    # handed a markdown file that is not a note pays for nothing.
    scope = Scope(docs_root, registry, git, rev_range, in_scope=None if sweep else set(targets))
    if to_check:
        scope.vocabulary = build_vocabulary(docs_root, registry, report, to_check, sweep)
    for path in to_check:
        if classify(path, docs_root, settings) == FORBIDDEN:
            report.error(
                path, f"{path.name} does not belong under {docs_root.name}/ -- {settings.forbidden_reason(path)}"
            )
            continue
        note = Note.read(path, registry)
        for rule in NOTE_RULES:
            rule(note, scope, report)

    for tree_rule in TREE_RULES:
        tree_rule(scope, report)
    return report, len(to_check)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="doc-marshal check",
        description="Validate notes against the registry. Exits 1 on any error; warnings never fail.",
    )
    parser.add_argument("paths", nargs="*", type=Path, help="notes to check")
    parser.add_argument("--all", action="store_true", help="sweep every note under the docs root (what CI runs)")
    parser.add_argument(
        "--range",
        help="git range whose notes count as edited, e.g. main..HEAD (default: the working tree; "
        "CI has no working-tree changes and must pass this to check freshness at all)",
    )
    parser.add_argument(
        "--skip-non-notes",
        action="store_true",
        help="silently skip paths that are not notes under the docs root, and exit 0 when there is "
        "no docs root at all -- for hooks handed every file a change touched",
    )
    parser.add_argument(
        "--format",
        choices=("text", "github"),
        default="text",
        help="github: one workflow command per finding, so a pull request shows it on the file",
    )
    add_docs_root_option(parser)
    args = parser.parse_args(argv)

    if not args.all and not args.paths:
        parser.error("name the notes to check, or pass --all")

    try:
        docs_root = find_docs_root(args.docs_root)
    except DocMarshalError:
        if args.skip_non_notes:
            return 0
        raise
    registry = load_registry(docs_root)

    targets = iter_checkable(docs_root, registry.settings) if args.all else [p.resolve() for p in args.paths]
    report, checked = run(
        docs_root,
        registry,
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
