"""`doc-marshal new`: create a note with the frontmatter and skeleton its type requires.

Frontmatter is mechanical -- the required fields follow from the type, `updated` is today, and a
numbered note's number is the highest existing one plus one. Every one of those is a rule someone
otherwise applies by hand and occasionally gets wrong, so the registry states them and this
command applies them.

    doc-marshal new reference docs/ledger/schema.md \\
        --summary "Fields of the ledger record." --code-ref src/ledger/schema.py
    doc-marshal new decision own-revenue-model --summary "Why the agent picks its own business."
    doc-marshal new context docs/payments --summary "Vocabulary of the payments subsystem."

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

from .config import load_registry
from .ontology import DocType, Registry
from .paths import DocMarshalError, find_docs_root, find_repo_root, rel_to
from .settings import NUMBER_PREFIX_RE, Settings


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
    """A complete note: frontmatter lines, H1, the type's skeleton, and `## Related` if required."""
    today = today or date.today().isoformat()
    skeleton = [line.replace("{today}", today) for line in spec.skeleton]
    lines = ["---", *meta, "---", "", f"# {title}", "", *skeleton]
    if spec.requires_related:
        lines += [
            "",
            "## Related",
            "",
            "<!-- One relative link per line, each with a clause saying why you would go there. -->",
        ]
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


def resolve_target(
    spec: DocType, given: str, docs_root: Path, repo_root: Path, title: str | None
) -> tuple[Path, str]:
    """Where the note goes and what its H1 says, from the type's placement rules."""
    if spec.numbered:
        slug = Path(given).stem
        folder = docs_root / spec.folder if spec.folder else docs_root
        number = next_number(folder)
        return folder / f"{number}-{slug}.md", f"{number} -- {title or title_from_slug(slug)}"
    if spec.fixed_name is not None:
        # The filename belongs to the type, so a directory is enough to say where it goes -- and
        # naming the file anyway is accepted rather than rejected on a technicality.
        path = Path(given)
        if not path.is_absolute():
            path = repo_root / path
        if path.name != spec.fixed_name:
            path = path / spec.fixed_name
        target = path.resolve()
        return target, title or f"{title_from_slug(target.parent.name)} context"
    path = Path(given)
    if not path.is_absolute():
        path = (repo_root / path) if (repo_root / path).parent.exists() else Path.cwd() / path
    target = path.resolve()
    return target, title or title_from_slug(target.stem)


def validate_placement(target: Path, spec: DocType, docs_root: Path, registry: Registry) -> None:
    settings: Settings = registry.settings
    if not target.is_relative_to(docs_root):
        raise DocMarshalError(f"a note must live under the docs root ({docs_root}): {target}")
    rel = target.relative_to(docs_root)
    # A type that claims a filename is exempt from the naming pattern for that name alone -- the
    # folders holding it are not.
    names = list(rel.parts[:-1]) if target.name in registry.fixed_names else [*rel.parts[:-1], target.stem]
    for part in names:
        if not settings.name_re.match(part):
            raise DocMarshalError(f"not kebab-case: {part}")
    if spec.folder is not None and target.parent != docs_root / spec.folder:
        raise DocMarshalError(f"a '{spec.name}' note belongs in {spec.folder}/ under the docs root")


def main(argv: list[str]) -> int:
    # The registry is needed to list the types in --help, so the docs root is resolved before the
    # parser is built. The resulting error message is the same one every other command prints.
    docs_root_arg = None
    if "--docs-root" in argv:
        docs_root_arg = argv[argv.index("--docs-root") + 1]
    docs_root = find_docs_root(docs_root_arg)
    registry = load_registry(docs_root)
    settings = registry.settings
    types = registry.enabled

    parser = argparse.ArgumentParser(
        prog="doc-marshal new", description="Scaffold a note the validator will accept."
    )
    parser.add_argument("type", choices=list(types))
    parser.add_argument(
        "path", help="path to the new note; a bare slug for a numbered type; a directory for a fixed-name type"
    )
    parser.add_argument(
        "--summary",
        required=True,
        help=f"one line, max {settings.summary_max} chars, stating what the doc is for",
    )
    parser.add_argument("--title", help="H1 text (default: derived from the filename)")
    for name, anchor in registry.anchor_fields.items():
        flag = "--" + name.replace("_", "-").rstrip("s")
        parser.add_argument(
            flag, action="append", default=[], dest=f"anchor_{name}", metavar="ENTRY",
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
    parser.add_argument("--docs-root", help="docs root (default: the directory holding the marker)")
    args = parser.parse_args(argv)

    repo_root = find_repo_root(docs_root)
    spec = types[args.type]
    today = date.today().isoformat()

    if len(args.summary) > settings.summary_max:
        raise DocMarshalError(
            f"summary must be one short line (max {settings.summary_max} chars), got {len(args.summary)}"
        )

    target, title = resolve_target(spec, args.path, docs_root, repo_root, args.title)
    validate_placement(target, spec, docs_root, registry)
    if target.exists():
        raise DocMarshalError(
            f"already exists -- edit it rather than replacing it: {rel_to(target, repo_root)}"
        )

    anchors = {name: getattr(args, f"anchor_{name}") for name in registry.anchor_fields}
    for name, anchor in registry.anchor_fields.items():
        if spec.requires_anchor(name) and not anchors[name]:
            flag = "--" + name.replace("_", "-").rstrip("s")
            raise DocMarshalError(
                f"type '{spec.name}' requires at least one {flag} ({anchor.contents})"
            )
        if anchor.on_spine:
            for ref in anchors[name]:
                if not (repo_root / ref).exists():
                    raise DocMarshalError(
                        f"{name} path does not exist (paths start at the repo root): {ref}"
                    )

    status = args.status or spec.default_status
    if spec.statuses:
        if status not in spec.statuses:
            raise DocMarshalError(f"a {spec.name} requires --status, one of {list(spec.statuses)}")
    elif args.status:
        raise DocMarshalError(f"type '{spec.name}' has no 'status' field")

    meta = frontmatter_lines(args.type, args.summary, today, status, anchors)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_note(title, meta, spec, today), encoding="utf-8")

    written = rel_to(target, repo_root)
    print(f"wrote {written}")
    print(f"next: write it, then doc-marshal check {written}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
