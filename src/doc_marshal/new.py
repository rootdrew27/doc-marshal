"""`doc-marshal new`: create a note with the frontmatter and template its type requires.

Frontmatter is mechanical -- the required fields follow from the type, `updated` is today, and a
numbered note's number is the highest existing one plus one. Every one of those is a policy someone
otherwise applies by hand and occasionally gets wrong, so the profile states them and this
command applies them.

    doc-marshal new reference docs/ledger/schema.md \\
        --summary "Fields of the ledger record." --code-ref src/ledger/schema.py
    doc-marshal new decision own-revenue-model --summary "Why the agent picks its own business."
    doc-marshal new nomenclature docs/payments --summary "Vocabulary of the payments subsystem."

For a numbered type, pass a bare slug: the number, the folder and the `NNNN -- ` title prefix are
all derived. For a type with a reserved filename, a directory is enough.

What is checked here is only what writing the file needs: a live type, a legal status, a path
under the docs tree, naming and placement. Anchors are not resolved and the type's minimum is
not enforced -- that is `check`'s job, and the note it writes fails `check` until its required
sections are written. The last line printed is the gate. An earlier version validated here as
well and still wrote notes `check` rejected, because two implementations of one policy drift.

The template writes every section the type requires and nothing else; a heading the type does
not require earns its place or is deleted.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from .config import add_docs_tree_option, resolve
from .discovery import find_repo_root
from .errors import DocMarshalError
from .git import Git
from .note import Note
from .ontology import DocType, Profile
from .paths import rel_to
from .policies import PLACEMENT_POLICIES, Scope
from .report import Report
from .settings import NOTE_SUFFIX, NUMBER_PREFIX_RE, NUMBER_TITLE_SEPARATOR


def title_from_slug(slug: str) -> str:
    words = slug.split("-")
    return " ".join([words[0].capitalize(), *words[1:]])


def next_number(folder: Path) -> str:
    """The next free number in a numbered type's folder: the highest present plus one."""
    highest = 0
    if folder.is_dir():
        for path in folder.glob(f"*{NOTE_SUFFIX}"):
            match = NUMBER_PREFIX_RE.match(path.stem)
            if match:
                highest = max(highest, int(match.group(1)))
    return f"{highest + 1:04d}"


def render_note(title: str, meta: list[str], spec: DocType, today: str | None = None) -> str:
    """A complete note: frontmatter lines, H1 and the type's template."""
    today = today or date.today().isoformat()
    template = [line.replace("{today}", today) for line in spec.template]
    lines = ["---", *meta, "---", "", f"# {title}", "", *template]
    return "\n".join([*lines, ""])


def frontmatter_lines(
    doc_type: str,
    summary: str,
    today: str,
    status: str | None = None,
    anchors: dict[str, list[str]] | None = None,
) -> list[str]:
    meta = [f"type: {doc_type}", f"updated: {today}", f"summary: {summary}"]
    if status:
        meta.append(f"status: {status}")
    for field_name, values in (anchors or {}).items():
        if values:
            meta.append(f"{field_name}:")
            meta += [f"  - {value}" for value in values]
    return meta


def resolve_target(spec: DocType, given: str, docs_tree: Path, title: str | None) -> tuple[Path, str]:
    """Where the note goes and what its H1 says, from the type's placement policies.

    A relative path is read from the current directory, the way every other tool reads one; the
    numbered types take a slug instead and place it themselves. Guessing between the current
    directory and the repo root was tried and put notes in the wrong place silently.
    """
    if spec.numbered:
        slug = Path(given).stem
        folder = spec.home(docs_tree)
        number = next_number(folder)
        return (
            folder / f"{number}-{slug}{NOTE_SUFFIX}",
            f"{number}{NUMBER_TITLE_SEPARATOR}{title or title_from_slug(slug)}",
        )
    if spec.reserved_filename is not None:
        # The filename belongs to the type, so a directory is enough to say where it goes -- and
        # naming the file anyway is accepted rather than rejected on a technicality.
        path = Path(given)
        if path.name != spec.reserved_filename:
            path = spec.reserved_path(path)
        target = path.resolve()
        return target, title or f"{title_from_slug(target.parent.name)} {spec.name}"
    path = Path(given)
    if path.suffix != NOTE_SUFFIX:
        path = path.with_name(path.name + NOTE_SUFFIX)
    target = path.resolve()
    return target, title or title_from_slug(target.stem)


def validate(target: Path, spec: DocType, docs_tree: Path, repo_root: Path, profile: Profile) -> None:
    """Refuse a path the file cannot be written at: outside the docs tree, misnamed, or misplaced
    for its type. The same naming and placement checks `check` runs, so the two cannot disagree
    about where a note goes."""
    if not target.is_relative_to(docs_tree):
        raise DocMarshalError(f"a note must live under the docs tree ({docs_tree}): {target}")
    report = Report(root=repo_root)
    note, scope = Note(target, meta={}, spec=spec), Scope(docs_tree, profile, Git(repo_root))
    for policy in PLACEMENT_POLICIES:
        policy(note, scope, report)
    if report.findings:
        raise DocMarshalError("\n".join(msg for _, _, msg in report.findings))


def main(argv: list[str]) -> int:
    # The profile is needed to list the types in --help, so the docs tree is resolved before the
    # full parser is built. The resulting error message is the same one every other command prints.
    tree_options = argparse.ArgumentParser(add_help=False)
    add_docs_tree_option(tree_options)
    docs_tree, profile = resolve(tree_options.parse_known_args(argv)[0].docs_tree)
    settings = profile.settings
    types = profile.enabled

    parser = argparse.ArgumentParser(
        prog="doc-marshal new",
        description="Scaffold a note with the frontmatter and sections its type requires.",
        parents=[tree_options],
    )
    parser.add_argument("type", choices=list(types))
    parser.add_argument(
        "path",
        help="path to the new note, from the current directory; a bare slug for a numbered type; "
        "a directory for a type with a reserved filename",
    )
    parser.add_argument(
        "--summary",
        required=True,
        help=f"one line, max {settings.summary_max} chars, stating what the doc is for",
    )
    parser.add_argument("--title", help="H1 text (default: derived from the filename)")
    for name, anchor in profile.anchor_fields.items():
        parser.add_argument(
            anchor.flag,
            action="append",
            default=[],
            dest=f"anchor_{name}",
            metavar="ENTRY",
            help=f"{name}: {anchor.contents} (repeatable)",
        )
    parser.add_argument(
        "--status",
        help="; ".join(
            f"{t.name}: {' | '.join(t.birth_statuses)}" + (f" (default {t.default_status})" if t.default_status else "")
            for t in types.values()
            if t.statuses
        ),
    )
    args = parser.parse_args(argv)

    repo_root = find_repo_root(docs_tree)
    spec = types[args.type]
    today = date.today().isoformat()

    if len(args.summary) > settings.summary_max:
        raise DocMarshalError(
            f"summary must be one short line (max {settings.summary_max} chars), got {len(args.summary)}"
        )

    target, title = resolve_target(spec, args.path, docs_tree, args.title)
    if target.exists():
        raise DocMarshalError(f"already exists -- edit it rather than replacing it: {rel_to(target, repo_root)}")

    status = args.status or spec.default_status
    if spec.statuses:
        if status not in spec.birth_statuses:
            raise DocMarshalError(f"a {spec.name} requires --status, one of {list(spec.birth_statuses)}")
    elif args.status:
        raise DocMarshalError(f"type '{spec.name}' has no 'status' field")

    anchors = {name: getattr(args, f"anchor_{name}") for name in profile.anchor_fields}
    validate(target, spec, docs_tree, repo_root, profile)

    meta = frontmatter_lines(args.type, args.summary, today, status, anchors)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_note(title, meta, spec, today), encoding="utf-8")

    written = rel_to(target, repo_root)
    print(f"wrote {written}")
    print(f"next: write it, then doc-marshal check {written}  (the scaffold does not pass until written)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
