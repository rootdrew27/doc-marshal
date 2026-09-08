"""The vocabulary in force for a note.

A structured type with a reserved filename (`nomenclature` in the standard profile) defines terms
and rules out aliases. This module reads those tables, resolves which of them bind a given note by
directory containment, reports a nested note redefining an ancestor's term, and compiles the alias
patterns. The scan that holds a note's text to it is `check_vocabulary` in `policies`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from .frontmatter import read_note
from .markdown import body_without_code, cell_items, cell_text, parse_table
from .ontology import DocType, Profile
from .paths import exists_exact, rel_to
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
    """The terms in force under each directory that holds a structured, reserved-filename note.

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


def vocabulary_sources(docs_tree: Path, spec: DocType, targets: list[Path], sweep: bool) -> list[Path]:
    """The notes of a vocabulary type this run needs: all of them in a sweep, otherwise the ones
    on each target's ancestor chain -- the only ones whose terms bind it, and the only ones a
    nested target can collide with. A targeted run therefore walks no further than its own path.
    """
    if sweep:
        return [path for path in targets if path.name == spec.reserved_filename]
    found: set[Path] = set()
    for target in targets:
        for directory in (target.parent, *target.parent.parents):
            if not directory.is_relative_to(docs_tree):
                break
            candidate = spec.reserved_path(directory)
            if exists_exact(docs_tree, candidate):
                found.add(candidate)
    return sorted(found)


def build_vocabulary(docs_tree: Path, profile: Profile, report: Report, targets: list[Path], sweep: bool) -> Vocabulary:
    """Collect the vocabulary notes' terms, reporting collisions down each chain.

    A nested note redefining an ancestor's term is an error: the point of the file is that one word
    has one meaning, and a repo where the meaning depends on which directory you are reading from
    has reintroduced exactly the ambiguity the vocabulary exists to remove. Reported on the nested
    note, and only when this run named it.
    """
    vocabulary = Vocabulary()
    in_scope = None if sweep else set(targets)
    for spec in profile.enabled.values():
        if not spec.is_vocabulary_source:
            continue
        notes = {path: read_terms(path, spec) for path in vocabulary_sources(docs_tree, spec, targets, sweep)}
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
                            f"'{term}' is already defined by {rel_to(other, docs_tree)} -- a "
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
    tabs, at most one line break -- and never across a paragraph break. Trees wrap text at a
    column, and an alias split by the wrap is the same alias.

    Cached: the same aliases bind every note under a directory, so each pattern is compiled once.
    """

    def edge(char: str) -> str:
        return r"\w" if re.match(r"\w", char) else rf"\w{re.escape(char)}"

    words = r"(?:[ \t]+\n?[ \t]*|\n[ \t]*)".join(re.escape(word) for word in alias.split())
    return re.compile(rf"(?<![{edge(alias[0])}]){words}(?![{edge(alias[-1])}])", re.IGNORECASE)
