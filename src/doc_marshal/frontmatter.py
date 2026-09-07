"""Read a note's frontmatter: the subset the convention allows, parsed strictly.

Pure and standard-library only. One parser for every command, so what a note declares cannot
differ between the validator, the index builder and the session renderer -- two frontmatter
parsers is a gap in the convention one level down.
"""

from __future__ import annotations

import re
from pathlib import Path

# The closing delimiter: `---` alone on its line. Searching for a bare "\n---" instead lets a body
# line like `---nope` close the block, silently truncating the frontmatter after it.
CLOSE_RE = re.compile(r"^---[ \t]*$", re.MULTILINE)

Meta = dict[str, "str | list[str]"]


def split_frontmatter(text: str) -> tuple[str | None, str]:
    """Return (frontmatter_block, body). frontmatter_block is None when absent."""
    if not text.startswith("---\n"):
        return None, text
    close = CLOSE_RE.search(text, 4)
    if close is None:
        return None, text
    return text[4 : close.start()], text[close.end() :]


def _unquote(value: str) -> str:
    """Strip one *matched* pair of surrounding quotes.

    Stripping quote characters unconditionally corrupts any value that merely ends in one:
    `it is not "done"` loses its closing quote and keeps the opening one, and the damage lands
    verbatim in the generated index.
    """
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def parse_frontmatter(block: str) -> Meta:
    """Parse the subset the convention uses: scalar fields and dash-item lists.

    Raises ValueError on anything richer, so an unparseable block fails loudly rather than
    validating as empty. This strictness is the convention, enforced at parse time -- it is why a
    YAML library is not used (SPEC.md section 9).
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
            current_list.append(_unquote(item[2:].strip()))
            continue
        if ":" not in line:
            raise ValueError(f"line {lineno}: expected 'key: value', got {line!r}")
        key, _, value = line.partition(":")
        key = key.strip()
        if key in result:
            raise ValueError(f"line {lineno}: duplicate key {key!r}")
        value = _unquote(value.strip())
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
    session renderer shows a note whose frontmatter will not parse verbatim rather than hiding it.
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
    the lead check and `affected` must agree that a scalar anchors nothing rather than one
    iterating its characters and the other skipping it.
    """
    value = meta.get(field)
    return [entry for entry in value if isinstance(entry, str)] if isinstance(value, list) else []
