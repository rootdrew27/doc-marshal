"""`doc-marshal index`: print the index -- every note with its `type:` and `summary:`.

The index is printed, never written into the docs tree. A file holding it is a document whose only
job is to agree with the filesystem, and it stops doing that the first time nobody regenerates it;
printed on demand, it cannot be stale.

    doc-marshal index
    doc-marshal index > notes.md   # keep a copy, outside the docs tree

A note missing `type:` or `summary:` is an error, not a gap to render around -- the index would
silently under-describe the docs. The notes that can be listed are, and the rest are reported.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from .config import add_docs_tree_option, resolve
from .frontmatter import read_note
from .ontology import Profile
from .paths import iter_notes


def plural(count: int) -> str:
    """ "1 note" rather than "1 notes" -- counts are read at the top of every session."""
    return "note" if count == 1 else "notes"


@dataclass(frozen=True)
class Note:
    path: Path  # relative to the docs tree
    doc_type: str
    summary: str


def collect(docs_tree: Path, profile: Profile) -> tuple[list[Note], list[str]]:
    """Return (notes, problems). Problems are notes that cannot be listed."""
    notes: list[Note] = []
    problems: list[str] = []
    for path in iter_notes(docs_tree, profile.settings):
        rel = path.relative_to(docs_tree)
        meta, _, _, error = read_note(path)
        if error is not None:
            problems.append(f"{rel}: {error}")
            continue
        assert meta is not None
        doc_type = meta.get("type")
        summary = meta.get("summary")
        missing = [
            name
            for name, value in (("type", doc_type), ("summary", summary))
            if not isinstance(value, str) or not value.strip()
        ]
        if missing:
            problems.append(f"{rel}: missing {' and '.join(missing)}")
            continue
        if profile.get(doc_type) is None:
            # The index names each note's type, so one outside the ontology would be published as
            # though it were real. The validator errors on this too; refusing here keeps the two
            # from disagreeing about what a note is.
            problems.append(f"{rel}: {profile.not_live(doc_type)}")
            continue
        assert isinstance(doc_type, str) and isinstance(summary, str)
        notes.append(Note(path=rel, doc_type=doc_type, summary=summary))
    return notes, problems


def report_problems(problems: list[str]) -> None:
    """Print the notes that could not be listed, and why."""
    if problems:
        print("not indexed -- every note needs 'type' and 'summary':", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)


def grouped(notes: list[Note]) -> dict[str, list[Note]]:
    """Notes by folder, folders in case-insensitive order, `.` for the top level."""
    groups: dict[str, list[Note]] = {}
    for note in notes:
        groups.setdefault(note.path.parent.as_posix(), []).append(note)
    return {folder: groups[folder] for folder in sorted(groups, key=str.lower)}


def folder_label(folder: str) -> str:
    return "(top level)" if folder == "." else folder


def render(notes: list[Note]) -> str:
    lines = [f"{len(notes)} {plural(len(notes))}, grouped by folder.", ""]
    for folder, members in grouped(notes).items():
        lines += [f"## {folder_label(folder)}", ""]
        for note in members:
            link = quote(note.path.name)
            if folder != ".":
                link = f"{quote(folder)}/{link}"
            lines.append(f"- [{note.path.stem}]({link}) -- `{note.doc_type}` -- {note.summary}")
        lines.append("")
    return "\n".join(lines)


def render_preview(notes: list[Note]) -> str:
    """Folder names with note counts, and nothing else -- the briefing's reduction.

    Uniform at every size, top level included (see docs/briefing.md): the full index grows linearly
    with the tree forever, and a summary of every note is a cost every session pays whether or not
    it opens a doc.
    """
    groups = grouped(notes)
    folders = ", ".join(f"{folder_label(folder)} {len(members)}" for folder, members in groups.items())
    return f"{len(notes)} {plural(len(notes))} in {len(groups)} folder(s):\n  {folders}"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="doc-marshal index", description="Print every note with its type and summary, grouped by folder."
    )
    add_docs_tree_option(parser)
    args = parser.parse_args(argv)

    docs_tree, profile = resolve(args.docs_tree)
    notes, problems = collect(docs_tree, profile)
    if notes:
        print(render(notes), end="")
    elif not problems:
        print("no notes yet")
    report_problems(problems)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
