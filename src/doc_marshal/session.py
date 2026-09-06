"""`doc-marshal session-context`: what a fresh session is given about the docs tree.

Three blocks, in the order they should be read (SPEC.md section 7):

1. The index preview -- folder names with note counts, and nothing else, ending with a pointer to
   the full index. Uniform reduction at every size, top level included: the full index grows
   linearly with the tree forever, and every session paid for it whether or not it opened a doc.
2. The docs root's nomenclature note, as its content rather than its file: the table as one line
   per term, then the prose sections as written. Frontmatter and HTML comments are for the
   validator and the author, not the session. The terms and the aliases they rule out are the
   content; a summary of a vocabulary is a second vocabulary. Only the root note is injected -- a
   nested one governs its subtree and is read on arriving there.
3. The compact `info` block -- the enabled types and their anchors.

This module decides *what* a session sees. Wiring it to a harness's session-start event is the
plugin's job; it only has to run this command and speak the hook's JSON.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import add_docs_root_option, load_registry
from .index import index_state, render_preview
from .info import render_session_types
from .markdown import cell_items, cell_text, parse_table, sections, strip_comments
from .ontology import DocType, Registry
from .paths import (
    DocMarshalError,
    exists_exact,
    find_docs_root,
    find_repo_root,
    read_note,
    rel_to,
)

REGENERATE = "doc-marshal index"


def index_block(docs_root: Path, registry: Registry, label: str) -> str:
    """The preview, with a warning ahead of it when the index no longer matches the notes.

    A session routing off a stale index is exactly when staleness matters, so it is computed here
    rather than left for CI to mention later. Any failure to answer counts as not stale: a broken
    hook must not manufacture a warning about the docs.
    """
    index_name = registry.settings.index_name
    try:
        state = index_state(docs_root, registry)
    except Exception:  # a hook must not fail the session over a docs problem
        return f"{label}/ is the documentation tree (doc-marshal). Its index could not be read."
    if not state.notes and state.problems:
        return (
            f"{label}/ is the documentation tree (doc-marshal), but no note could be indexed. "
            f"Run `doc-marshal check --all`."
        )
    lines = [f"{label}/ is the documentation tree (doc-marshal). {render_preview(state.notes)}"]
    lines.append(
        f"Full list with each note's type and summary: {label}/{index_name} "
        f"(generated -- `{REGENERATE}` regenerates it; never edit it)."
    )
    if state.stale:
        lines.insert(
            0,
            f"WARNING: {label}/{index_name} no longer matches the notes it is generated from -- it may "
            f"name docs that moved or omit docs that exist. Regenerate it with `{REGENERATE}`.",
        )
    if state.problems:
        lines.append("Notes that could not be indexed: " + "; ".join(state.problems))
    return "\n".join(lines)


def render_nomenclature(path: Path, spec: DocType) -> str:
    """A nomenclature note as a session should read it.

    The table becomes one line per term -- the key column, the body column, then each scanned
    column under its own name -- read through the same parser the validator uses, so a reformatted
    table cannot leak in as text. The other sections follow as written. HTML comments are stripped throughout, and the
    frontmatter and title are not emitted at all: the block's own sentence says what this is.
    Falls back to the body verbatim when the table is not the shape the registry expects, because
    a malformed table is `check`'s finding and must not hide the vocabulary.
    """
    structure = spec.structure
    _, body, text, error = read_note(path)
    source = strip_comments(body if error is None else text).strip()
    if structure is None:
        return source
    header, rows, _ = parse_table(source, structure.table_in)
    if not structure.accepts(header):
        return source
    lines: list[str] = [f"**{structure.table_in}**", ""]
    for row in rows:
        entry = f"- **{cell_text(row[structure.key_column])}** -- {row[structure.body_column].rstrip('.')}."
        for column in structure.scanned_columns:
            if items := cell_items(row[column]):
                entry += f" {column}: {', '.join(items)}."
        lines.append(entry)
    for name, section_lines in sections(source):
        content = "\n".join(section_lines).strip()
        if name != structure.table_in and content:
            lines += ["", f"**{name}**", "", content]
    return "\n".join(lines)


def nomenclature_blocks(docs_root: Path, registry: Registry, label: str) -> list[str]:
    """The docs root's fixed-name, root-required notes, rendered for reading."""
    blocks: list[str] = []
    for spec in registry.root_notes:
        path = spec.fixed_path(docs_root)
        if not exists_exact(docs_root, path):
            blocks.append(
                f"{label}/{spec.fixed_name} is missing. The docs tree expects one, and notes written "
                f"without it will not share a vocabulary. `doc-marshal new {spec.name} {label}` scaffolds it."
            )
            continue
        blocks.append(
            f"The project's shared vocabulary follows, from {label}/{spec.fixed_name}. Use these terms "
            "in documentation and in code, and avoid the aliases they rule out. A directory with its "
            f"own {spec.fixed_name} adds terms for its subtree.\n\n" + render_nomenclature(path, spec)
        )
    return blocks


def session_context(docs_root: Path, registry: Registry) -> str:
    """Everything a session is given about the docs tree, in the order it should be read."""
    label = rel_to(docs_root, find_repo_root(docs_root)).as_posix()
    blocks = [
        index_block(docs_root, registry, label),
        *nomenclature_blocks(docs_root, registry, label),
        render_session_types(registry),
    ]
    return "\n\n".join(block for block in blocks if block)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="doc-marshal session-context",
        description="Print what a fresh session is given about the docs tree.",
    )
    add_docs_root_option(parser)
    parser.add_argument(
        "--quiet-if-absent",
        action="store_true",
        help="print nothing and exit 0 when there is no docs root -- for a hook installed everywhere",
    )
    args = parser.parse_args(argv)
    try:
        docs_root = find_docs_root(args.docs_root)
    except DocMarshalError:
        if args.quiet_if_absent:
            return 0
        raise
    print(session_context(docs_root, load_registry(docs_root)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
