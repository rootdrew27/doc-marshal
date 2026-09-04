"""`doc-marshal new`: create a note with the frontmatter and skeleton its type requires.

Frontmatter is mechanical -- the required fields follow from the type, `updated` is today, and a
numbered note's number is the highest existing one plus one. Every one of those is a rule someone
otherwise applies by hand and occasionally gets wrong, so the registry states them and this
command applies them.

    doc-marshal new reference docs/ledger/schema.md \\
        --summary "Fields of the ledger record." --code-ref src/ledger/schema.py
    doc-marshal new decision own-revenue-model --summary "Why the agent picks its own business."
    doc-marshal new nomenclature docs/payments --summary "Vocabulary of the payments subsystem."

For a numbered type, pass a bare slug: the number, the folder and the `NNNN -- ` title prefix are
all derived. For a fixed-name type, a directory is enough. Anything the type requires and you did
not supply is an error before anything is written -- a note that fails the validator on creation
is worse than no note.

The skeleton is a starting point, not an outline to fill in mechanically: delete a heading that
earns nothing rather than writing a paragraph under it because it is there.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from .check import Report, check_anchor, check_location, check_naming
from .config import add_docs_root_option, resolve
from .ontology import DocType, Registry
from .paths import DocMarshalError, find_repo_root, rel_to
from .settings import NUMBER_PREFIX_RE


def title_from_slug(slug: str) -> str:
    words = slug.split("-")
    return " ".join([words[0].capitalize(), *words[1:]])


def next_number(folder: Path) -> str:
    """The next free number in a numbered type's folder: the highest present plus one."""
    highest = 0
    if folder.is_dir():
        for path in folder.glob("*.md"):
            match = NUMBER_PREFIX_RE.match(path.stem)
            if match:
                highest = max(highest, int(match.group(1)))
    return f"{highest + 1:04d}"


def render_note(title: str, meta: list[str], spec: DocType, today: str | None = None) -> str:
    """A complete note: frontmatter lines, H1 and the type's skeleton."""
    today = today or date.today().isoformat()
    skeleton = [line.replace("{today}", today) for line in spec.skeleton]
    lines = ["---", *meta, "---", "", f"# {title}", "", *skeleton]
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


def resolve_target(spec: DocType, given: str, docs_root: Path, title: str | None) -> tuple[Path, str]:
    """Where the note goes and what its H1 says, from the type's placement rules.

    A relative path is read from the current directory, the way every other tool reads one; the
    numbered types take a slug instead and place it themselves. Guessing between the current
    directory and the repo root was tried and put notes in the wrong place silently.
    """
    if spec.numbered:
        slug = Path(given).stem
        folder = spec.home(docs_root)
        number = next_number(folder)
        return folder / f"{number}-{slug}.md", f"{number} -- {title or title_from_slug(slug)}"
    if spec.fixed_name is not None:
        # The filename belongs to the type, so a directory is enough to say where it goes -- and
        # naming the file anyway is accepted rather than rejected on a technicality.
        path = Path(given)
        if path.name != spec.fixed_name:
            path = path / spec.fixed_name
        target = path.resolve()
        return target, title or f"{title_from_slug(target.parent.name)} {spec.name}"
    path = Path(given)
    if path.suffix != ".md":
        path = path.with_name(path.name + ".md")
    target = path.resolve()
    return target, title or title_from_slug(target.stem)


def validate(
    target: Path, spec: DocType, anchors: dict[str, list[str]], docs_root: Path, repo_root: Path, registry: Registry
) -> None:
    """Refuse a note the validator would reject: the same naming, placement and anchor checks
    `check` runs, against the path and anchors this note is about to be written with. One
    implementation of each rule, so `new` cannot write what `check` then fails."""
    if not target.is_relative_to(docs_root):
        raise DocMarshalError(f"a note must live under the docs root ({docs_root}): {target}")
    report = Report(root=repo_root)
    check_naming(target, docs_root, registry, report)
    check_location(target, spec, docs_root, registry, report)
    for name, anchor in registry.anchor_fields.items():
        if anchors[name]:
            check_anchor(target, anchor, anchors[name], docs_root, repo_root, registry, report)
    if report.findings:
        raise DocMarshalError("\n".join(msg for _, _, msg in report.findings))


def main(argv: list[str]) -> int:
    # The registry is needed to list the types in --help, so the docs root is resolved before the
    # full parser is built. The resulting error message is the same one every other command prints.
    root_options = argparse.ArgumentParser(add_help=False)
    add_docs_root_option(root_options)
    docs_root, registry = resolve(root_options.parse_known_args(argv)[0].docs_root)
    settings = registry.settings
    types = registry.enabled

    parser = argparse.ArgumentParser(
        prog="doc-marshal new",
        description="Scaffold a note the validator will accept.",
        parents=[root_options],
    )
    parser.add_argument("type", choices=list(types))
    parser.add_argument(
        "path",
        help="path to the new note, from the current directory; a bare slug for a numbered type; "
        "a directory for a fixed-name type",
    )
    parser.add_argument(
        "--summary",
        required=True,
        help=f"one line, max {settings.summary_max} chars, stating what the doc is for",
    )
    parser.add_argument("--title", help="H1 text (default: derived from the filename)")
    for name, anchor in registry.anchor_fields.items():
        parser.add_argument(
            anchor.flag, action="append", default=[], dest=f"anchor_{name}", metavar="ENTRY",
            help=f"{name}: {anchor.contents} (repeatable)",
        )
    parser.add_argument(
        "--status",
        help="; ".join(
            f"{t.name}: {' | '.join(t.statuses)}"
            + (f" (default {t.default_status})" if t.default_status else "")
            for t in types.values()
            if t.statuses
        ),
    )
    args = parser.parse_args(argv)

    repo_root = find_repo_root(docs_root)
    spec = types[args.type]
    today = date.today().isoformat()

    if len(args.summary) > settings.summary_max:
        raise DocMarshalError(
            f"summary must be one short line (max {settings.summary_max} chars), got {len(args.summary)}"
        )

    target, title = resolve_target(spec, args.path, docs_root, args.title)
    if target.exists():
        raise DocMarshalError(
            f"already exists -- edit it rather than replacing it: {rel_to(target, repo_root)}"
        )

    status = args.status or spec.default_status
    if spec.statuses:
        if status not in spec.statuses:
            raise DocMarshalError(f"a {spec.name} requires --status, one of {list(spec.statuses)}")
    elif args.status:
        raise DocMarshalError(f"type '{spec.name}' has no 'status' field")

    anchors = {name: getattr(args, f"anchor_{name}") for name in registry.anchor_fields}
    if spec.anchors_required(status) and not any(anchors[name] for name in spec.requires):
        flags = " or ".join(registry.anchor_fields[name].flag for name in spec.requires)
        since = f" once its status is '{spec.requires_from}'" if spec.requires_from else ""
        raise DocMarshalError(f"type '{spec.name}' requires at least one {flags}{since}")
    validate(target, spec, anchors, docs_root, repo_root, registry)

    meta = frontmatter_lines(args.type, args.summary, today, status, anchors)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_note(title, meta, spec, today), encoding="utf-8")

    written = rel_to(target, repo_root)
    print(f"wrote {written}")
    print(f"next: write it, then doc-marshal check {written}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
