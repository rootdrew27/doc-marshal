"""One note, read once.

A `Note` is the unit every per-note rule takes: the path, what the frontmatter says or why it
would not parse, the live type it declares, and the body in the readings the rules take of it.
Building it once means the reader, the type lookup and the three views are each computed one
time per note, and no rule can read the note differently from another.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from .frontmatter import Meta, read_note
from .markdown import body_without_code, strip_comments, without_code_spans
from .ontology import DocType, Registry


@dataclass(frozen=True)
class Note:
    """A note as the rules see it. `meta` and `error` are what `read_note` returns: exactly one of
    them is None. `spec` is the registry's live type of that name, or None when the frontmatter
    did not parse or names no live type -- the frontmatter rule reports which. A note that does
    not exist yet, as `new` checks a placement, is `Note(path, meta={}, spec=spec)`: empty
    frontmatter, no body, the type it is about to be given.

    Three views of the body, each computed once on first use. Comments come out first, so a
    comment spanning two headings hides the second the way markdown renders it and a section
    holding only its scaffold comment is blank; then fenced blocks, which are content but not
    prose; then code spans, which quote a name rather than use it. The raw `body` still measures
    the size cap.
    """

    path: Path
    body: str = ""  # below the frontmatter, raw
    meta: Meta | None = None
    error: str | None = None
    spec: DocType | None = None

    @cached_property
    def plain(self) -> str:
        """The body without HTML comments."""
        return strip_comments(self.body)

    @cached_property
    def prose(self) -> str:
        """`plain` without fenced code blocks."""
        return body_without_code(self.plain)

    @cached_property
    def scan(self) -> str:
        """`prose` without inline code spans -- what the alias scan and the link check read."""
        return without_code_spans(self.prose)

    @classmethod
    def read(cls, path: Path, registry: Registry) -> Note:
        """Read the note at `path` and resolve its type against `registry`."""
        meta, body, _, error = read_note(path)
        spec = registry.get(meta.get("type")) if meta is not None else None
        return cls(path, body, meta, error, spec)
