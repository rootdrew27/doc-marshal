"""Read a note's frontmatter: the subset the convention allows, parsed strictly.

Pure and standard-library only. One parser for every command, so what a note declares cannot
differ between the validator, the index builder and the briefing renderer -- two frontmatter
parsers is a gap in the convention one level down.
"""

from __future__ import annotations

import re
from pathlib import Path

# The closing delimiter: `---` alone on its line. Searching for a bare "\n---" instead lets a body
# line like `---nope` close the block, silently truncating the frontmatter after it.
CLOSE_RE = re.compile(r"^---[ \t]*$", re.MULTILINE)

# The characters a plain (unquoted) YAML scalar may not open with. `-`, `?` and `:` are indicators
# only where a space follows them, so `--pins` and `0.4.0-rc1` stay plain; the rest always are.
SPACED_INDICATORS = "-?:"
INDICATORS = ",[]{}#&*!|>'\"%@`"

Meta = dict[str, "str | list[str]"]


def split_frontmatter(text: str) -> tuple[str | None, str]:
    """Return (frontmatter_block, body). frontmatter_block is None when absent."""
    if not text.startswith("---\n"):
        return None, text
    close = CLOSE_RE.search(text, 4)
    if close is None:
        return None, text
    return text[4 : close.start()], text[close.end() :]


def unquotable(value: str) -> str | None:
    """Why a YAML parser will not read `value` back as itself unquoted, or None when it will.

    The parser here reads a plain scalar to the end of its line whatever it holds, so a summary
    carrying `: ` round-trips through every doc-marshal command untouched. Every other reader of
    the tree -- an editor's markdown preview, a static site generator, a CI step in another
    language -- runs a real YAML parser, which reads that same line as a nested mapping and refuses
    the note. The convention is what YAML allows, enforced on both sides: `quote_scalar` writes
    such a value quoted, and `parse_frontmatter` rejects it unquoted rather than passing on a note
    only this package can read.
    """
    if not value:
        return None
    if value[0] in INDICATORS or (value[0] in SPACED_INDICATORS and value[1:2] in ("", " ")):
        return f"it opens with {value[0]!r}"
    if ": " in value or value.endswith(":"):
        return "it carries ': ', which reads as a nested mapping"
    if " #" in value:
        return "it carries ' #', which opens a comment"
    return None


def quote_scalar(value: str) -> str:
    """`value` as a frontmatter scalar: plain where YAML reads it back unchanged, quoted where not."""
    if unquotable(value) is None:
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _is_quoted(value: str) -> bool:
    """Whether `value` carries a *matched* pair of surrounding quotes.

    Reading an unmatched one as quoted corrupts any value that merely ends in a quote:
    `it is not "done"` loses its closing quote and keeps the opening one, and the damage lands
    verbatim in the generated index.
    """
    return len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'"


def _unquote(value: str) -> str:
    """Strip one matched pair of surrounding quotes, and the escapes inside a double-quoted value."""
    if not _is_quoted(value):
        return value
    inner = value[1:-1]
    # Single-quoted YAML holds its content literally; double-quoted spells `"` and `\` with a
    # backslash, which is how `quote_scalar` writes a value carrying either.
    return re.sub(r'\\(["\\])', r"\1", inner) if value[0] == '"' else inner


def _read_value(value: str, lineno: int, what: str) -> str:
    """One scalar, rejected where a YAML parser would not read it back as written."""
    value = value.strip()
    problem = None if _is_quoted(value) else unquotable(value)
    if problem is not None:
        raise ValueError(f"line {lineno}: {what} must be quoted -- {problem}")
    return _unquote(value)


def parse_frontmatter(block: str) -> Meta:
    """Parse the subset the convention uses: scalar fields and dash-item lists.

    Raises ValueError on anything richer, so an unparseable block fails loudly rather than
    validating as empty. This strictness is the convention, enforced at parse time -- it is why a
    YAML library is not used (see docs/dependency-policy.md).
    """
    result: Meta = {}
    current_list: list[str] | None = None
    for lineno, raw in enumerate(block.splitlines(), start=2):
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        if line.startswith((" ", "\t", "-")):
            item = line.strip()
            if not item.startswith("- "):
                raise ValueError(f"line {lineno}: expected a '- ' list item, got {line!r}")
            if current_list is None:
                raise ValueError(f"line {lineno}: list item with no preceding key")
            current_list.append(_read_value(item[2:], lineno, "list item"))
            continue
        if ":" not in line:
            raise ValueError(f"line {lineno}: expected 'key: value', got {line!r}")
        key, _, value = line.partition(":")
        # The space is not decoration. `type:spec` partitions here into a key and a value, and is a
        # plain scalar -- not a mapping -- to every YAML parser, which then refuses the block.
        if value and not value.startswith((" ", "\t")):
            raise ValueError(f"line {lineno}: expected a space after the colon, got {line!r}")
        key = key.strip()
        if key in result:
            raise ValueError(f"line {lineno}: duplicate key {key!r}")
        value = _read_value(value, lineno, f"the value of {key!r}")
        if value:
            result[key] = value
            current_list = None
        else:
            current_list = []
            result[key] = current_list
    return result


def read_note(path: Path) -> tuple[Meta | None, str, str, str | None]:
    """Read a note as (metadata, body, whole text, error). Exactly one of metadata/error is None.

    The whole text is returned alongside the body for the one reader that falls back to it: the
    briefing renderer shows a note whose frontmatter will not parse verbatim rather than hiding it.
    """
    text = path.read_text(encoding="utf-8")
    block, body = split_frontmatter(text)
    if block is None:
        return None, body, text, "no frontmatter -- every note declares 'type', 'updated', and 'summary'"
    try:
        return parse_frontmatter(block), body, text, None
    except ValueError as exc:
        return None, body, text, f"unparseable frontmatter -- {exc}"


def anchor_entries(meta: Meta, field: str) -> list[str]:
    """The string entries of an anchor field, or nothing when the field is absent or not a list.

    One reading for every consumer: `check_anchor` reports a scalar as an error, and after that
    the lead check and `drifted` must agree that a scalar anchors nothing rather than one
    iterating its characters and the other skipping it.
    """
    value = meta.get(field)
    return [entry for entry in value if isinstance(entry, str)] if isinstance(value, list) else []
