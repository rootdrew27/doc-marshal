"""Reading markdown: fences, headings, comments, code spans, `##` sections and table rows.

Nothing here knows the registry or reports a finding. These are the one reading of each shape,
consumed by the validator, the vocabulary reader and the session renderer, so no two of them can disagree about
where code starts, where a section ends or what a table row holds.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`]*`")


def _fenced_lines(text: str) -> Iterator[tuple[str, bool]]:
    """Each line of `text` with whether it is code: inside a fenced block, or a fence itself.

    One implementation, so the link checker, the heading readers and the section reader cannot
    disagree about where code starts.
    """
    in_fence = False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            yield line, True
        else:
            yield line, in_fence


def _outside_fences(text: str) -> Iterator[str]:
    """The lines of `text` not inside a fenced code block, fences themselves dropped."""
    return (line for line, fenced in _fenced_lines(text) if not fenced)


def heading_lines(text: str) -> Iterator[tuple[int, str]]:
    """Every heading outside fences as (level, text), in document order."""
    for line in _outside_fences(text):
        match = HEADING_RE.match(line)
        if match:
            yield len(match.group(1)), match.group(2).strip()


def headings(text: str) -> set[str]:
    """Heading anchors in GitHub's slug form, skipping fenced code blocks.

    Repeated headings are disambiguated the way GitHub does it, by suffixing the later ones with
    `-1`, `-2` and so on. Collapsing them made a *correct* link to the second `## Setup` report as
    a missing anchor -- an error, so valid markdown failed the build.
    """
    anchors: set[str] = set()
    seen: dict[str, int] = {}
    for _, heading in heading_lines(text):
        slug = heading.lower()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"\s+", "-", slug)
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        anchors.add(slug if count == 0 else f"{slug}-{count}")
    return anchors


def body_without_code(text: str) -> str:
    """Body with fenced blocks removed, so example links in code are not validated."""
    return "\n".join(_outside_fences(text))


def strip_comments(text: str) -> str:
    """Text without its HTML comments. The one reading, shared with the session renderer: a
    comment is for the author and the validator, so it is neither content a section is
    populated by, prose the alias scan reads, nor text a session is shown."""
    return COMMENT_RE.sub("", text)


def without_code_spans(text: str) -> str:
    """Text without its inline code spans: a backticked name is quoted, not used, so neither the
    alias scan nor the link check reads it."""
    return INLINE_CODE_RE.sub("", text)


# --- sections and tables -------------------------------------------------------------------------

SECTION_RE = re.compile(r"^##\s+(.*)$")
# A markdown table row: at least one pipe-delimited cell between outer pipes.
TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?$")
# Cells naming nothing. A structured table says "no aliases" with a dash rather than a blank,
# because a blank cell reads as an unfinished row.
EMPTY_CELLS = frozenset({"", "-", "--", "n/a", "none"})

Row = dict[str, str]  # a well-formed table row, cell by column name


def sections(text: str) -> list[tuple[str, list[str]]]:
    """The `##` sections of a note, each heading with the lines under it, in document order.

    The one reading of where a section starts and ends: the shape check, the table reader, the
    size cap and the session renderer all consume this rather than scanning for headings
    themselves. A `##` inside a fenced block is content, so the raw body can be handed in. Text
    before the first heading is dropped. Repeated headings stay repeated, so a shape check sees
    them.
    """
    found: list[tuple[str, list[str]]] = []
    for line, fenced in _fenced_lines(text):
        match = None if fenced else SECTION_RE.match(line)
        if match:
            found.append((match.group(1).strip(), []))
        elif found:
            found[-1][1].append(line)
    return found


def cell_text(cell: str) -> str:
    """A cell's text without the emphasis or backticks a writer wrapped it in."""
    return cell.strip().strip("*`")


def cell_items(cell: str) -> list[str]:
    """A comma-separated cell as its items, none when the cell says there are none."""
    if cell.strip().lower() in EMPTY_CELLS:
        return []
    return [item for item in (cell_text(part) for part in cell.split(",")) if item]


CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")


def _cells(line: str) -> list[str]:
    """The cells of a markdown table row, outer pipes dropped. `\\|` is a literal pipe inside a
    cell, as GitHub reads it, not a boundary."""
    return [cell.strip().replace("\\|", "|") for cell in CELL_SPLIT_RE.split(line.strip().strip("|"))]


def parse_table(prose: str, section: str) -> tuple[list[str], list[Row], list[list[str]]]:
    """The table under `## {section}`: its header, its well-formed rows keyed by column, and the
    rows whose cell count does not match the header.

    Returns nothing when the section or its table is absent; reporting that is
    `check_structure`'s job, and every caller wants the same tolerant read.
    """
    lines = next((body for name, body in sections(prose) if name == section), [])
    header: list[str] = []
    rows: list[Row] = []
    malformed: list[list[str]] = []
    for line in lines:
        if not TABLE_ROW_RE.match(line):
            continue
        cells = _cells(line)
        if not header:
            header = cells
        elif all(SEPARATOR_CELL_RE.match(cell) for cell in cells):
            continue
        elif len(cells) == len(header):
            rows.append(dict(zip(header, cells, strict=True)))
        else:
            malformed.append(cells)
    return header, rows, malformed


def table_chars(text: str, section: str) -> int:
    """The characters the table's rows take -- header, separator and body, newlines included."""
    return sum(
        len(line) + 1 for name, lines in sections(text) if name == section for line in lines if TABLE_ROW_RE.match(line)
    )
