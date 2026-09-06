"""The vocabulary in force for a note, and the scan that holds prose to it.

A structured, fixed-name type (`nomenclature` in the standard preset) defines terms and rules out
aliases. This module reads those tables, resolves which of them bind a given note by directory
containment, reports a nested note redefining an ancestor's term, and warns when prose uses an
alias the vocabulary rules out.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from .markdown import body_without_code, cell_items, cell_text, parse_table
from .ontology import DocType, Registry
from .paths import Meta, exists_exact, read_note, rel_to
from .report import Report


def read_terms(path: Path, spec: DocType) -> dict[str, list[str]]:
    """A structured note's terms, each mapped to the aliases other notes are checked against.

    Tolerant by design: a note whose table is malformed contributes nothing rather than raising,
    because `check_structure` already reports the shape and one bad table must not disable the
    vocabulary of every other.
    """
    structure = spec.structure
    if structure is None:
        return {}
    meta, body, _, error = read_note(path)
    if error is not None or meta is None or meta.get("type") != spec.name:
        return {}
    header, rows, _ = parse_table(body_without_code(body), structure.table_in)
    if not structure.accepts(header):
        return {}
    terms: dict[str, list[str]] = {}
    for row in rows:
        key = cell_text(row[structure.key_column])
        if key:
            terms[key] = [alias for column in structure.scanned_columns for alias in cell_items(row[column])]
    return terms


@dataclass
class Vocabulary:
    """The terms in force under each directory that holds a structured, fixed-name note.

    Resolution is by containment rather than by exact directory, so a note deep in the tree
    inherits every nomenclature note above it. `additive` is what makes merging them safe: no two
    nomenclature notes in one chain may define the same term, so the merge cannot depend on order.
    """

    by_dir: dict[Path, dict[str, list[str]]] = field(default_factory=dict)

    def aliases_for(self, path: Path) -> dict[str, str]:
        """Every banned alias in force for a note, mapped to the term to use instead."""
        banned: dict[str, str] = {}
        for directory in sorted(self.by_dir, key=lambda d: len(d.parts)):
            if not path.parent.is_relative_to(directory):
                continue
            for term, aliases in self.by_dir[directory].items():
                for alias in aliases:
                    banned[alias.lower()] = term
        return banned


def vocabulary_sources(docs_root: Path, spec: DocType, targets: list[Path], sweep: bool) -> list[Path]:
    """The notes of a vocabulary type this run needs: all of them in a sweep, otherwise the ones
    on each target's ancestor chain -- the only ones whose terms bind it, and the only ones a
    nested target can collide with. A targeted run therefore walks no further than its own path.
    """
    if sweep:
        return [path for path in targets if path.name == spec.fixed_name]
    found: set[Path] = set()
    for target in targets:
        for directory in (target.parent, *target.parent.parents):
            if not directory.is_relative_to(docs_root):
                break
            candidate = spec.fixed_path(directory)
            if exists_exact(docs_root, candidate):
                found.add(candidate)
    return sorted(found)


def build_vocabulary(
    docs_root: Path, registry: Registry, report: Report, targets: list[Path], sweep: bool
) -> Vocabulary:
    """Collect the vocabulary notes' terms, reporting collisions down each chain.

    A nested note redefining an ancestor's term is an error: the point of the file is that one word
    has one meaning, and a repo where the meaning depends on which directory you are reading from
    has reintroduced exactly the ambiguity the vocabulary exists to remove. Reported on the nested
    note, and only when this run named it.
    """
    vocabulary = Vocabulary()
    in_scope = None if sweep else set(targets)
    for spec in registry.enabled.values():
        if not spec.is_vocabulary_source:
            continue
        notes = {path: read_terms(path, spec) for path in vocabulary_sources(docs_root, spec, targets, sweep)}
        for path, terms in notes.items():
            vocabulary.by_dir[path.parent] = terms
            if not spec.additive or (in_scope is not None and path not in in_scope):
                continue
            for other, ancestor_terms in notes.items():
                if other.parent == path.parent or not path.parent.is_relative_to(other.parent):
                    continue
                above = {term.lower() for term in ancestor_terms}
                for term in sorted(terms):
                    if term.lower() in above:
                        report.error(
                            path,
                            f"'{term}' is already defined by {rel_to(other, docs_root)} -- a "
                            f"nested '{spec.name}' note adds terms, it never redefines them",
                        )
    return vocabulary


@cache
def alias_re(alias: str) -> re.Pattern[str]:
    """A whole-word match for an alias, robust to aliases that start or end in a non-word character.

    `\\b` misbehaves there: `\\b.env\\b` needs a word character right before the dot, so `.env` at
    the start of a sentence never matches, and `C++` can never end at a word boundary. Lookarounds
    ask the right question -- not touching a word character on either side -- for every alias. An
    alias whose edge is itself punctuation must also not touch a repeat of that character, so
    `C+++` and `..env` are not sightings of `C++` and `.env`.

    A multi-word alias matches across whatever whitespace one paragraph wraps it with -- spaces,
    tabs, at most one line break -- and never across a paragraph break. Trees wrap prose at a
    column, and an alias split by the wrap is the same alias.

    Cached: the same aliases bind every note under a directory, so each pattern is compiled once.
    """

    def edge(char: str) -> str:
        return r"\w" if re.match(r"\w", char) else rf"\w{re.escape(char)}"

    words = r"(?:[ \t]+\n?[ \t]*|\n[ \t]*)".join(re.escape(word) for word in alias.split())
    return re.compile(rf"(?<![{edge(alias[0])}]){words}(?![{edge(alias[-1])}])", re.IGNORECASE)


def check_vocabulary(path: Path, spec: DocType, meta: Meta, scan: str, vocabulary: Vocabulary, report: Report) -> None:
    """Prose uses the vocabulary's terms rather than the aliases it rules out.

    A warning, not an error: the scan is a word match and cannot see intent, and a false positive
    that blocks a commit would be worse than the drift it catches.

    The frontmatter `summary` is scanned with the body: it is the one line every session reads.
    `scan` is the body with its comments, fenced blocks and code spans already removed: comments
    are notes to the author, and a banned alias is routinely the literal name of a field or an
    API, with backticks the way you say so. Two exemptions, both structural. An append-only type
    is skipped because its wording cannot lawfully be corrected. A vocabulary note is skipped
    because the aliases are its content.
    """
    if spec.append_only or spec.is_vocabulary_source:
        return
    banned = vocabulary.aliases_for(path)
    if not banned:
        return
    summary = meta.get("summary")
    text = f"{summary}\n\n{scan}" if isinstance(summary, str) else scan
    for alias in sorted(banned):
        if alias_re(alias).search(text):
            report.warn(
                path,
                f"'{alias}' is an alias the vocabulary rules out -- use "
                f"'{banned[alias]}' instead, or put it in backticks if it is a literal name",
            )
