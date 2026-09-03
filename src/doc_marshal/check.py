"""`doc-marshal check`: validate notes against the registry -- naming, frontmatter, anchors, links,
location, structure, vocabulary, prose.

Checks the files named on the command line: a run fixes the docs it touched, not every doc under
the docs root. `--all` is the sweep CI runs.

    doc-marshal check docs/ledger/schema.md docs/decisions/0004-parking.md
    doc-marshal check --all --range main..HEAD

Exits 1 if any error is reported. Warnings never fail the run. Every rule that varies by type is
read off the registry rather than branched on by name, so a new type is a registry entry and
nothing here changes.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import unquote, urlparse

from .affected import matches
from .config import load_registry
from .ontology import AnchorField, DocType, Registry, Structure
from .paths import (
    FORBIDDEN,
    DocMarshalError,
    Meta,
    changed_paths,
    classify,
    edited_notes,
    find_docs_root,
    find_repo_root,
    is_checkable,
    iter_checkable,
    iter_named,
    read_note,
    rel_to,
)
from .settings import Settings

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")
INLINE_CODE_RE = re.compile(r"`[^`]*`")
# The convention writes the em dash as ` -- `, which survives every editor and diff tool. A literal
# one is a warning, not an error: quoted material may legitimately carry the character.
EM_DASH = "—"
WIKILINK_RE = re.compile(r"\[\[[^\]]+\]\]")
HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")

# How a finding is printed. The plugin's PostToolUse hook selects on these, so they are a contract
# rather than incidental formatting.
ERROR_PREFIX = "ERROR: "
WARN_PREFIX = "warn:  "


@dataclass
class Report:
    """Findings, each prefixed with the note's path relative to `root` -- the repository root, so a
    line reads the same in CI, in a pre-commit hook and in the plugin's hook output, whatever the
    working directory and however the target was spelled."""

    root: Path | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    findings: list[tuple[str, Path, str]] = field(default_factory=list)  # (level, path, message)

    def error(self, path: Path, msg: str) -> None:
        self.errors.append(f"{self.display(path)}: {msg}")
        self.findings.append(("error", self.display(path), msg))

    def warn(self, path: Path, msg: str) -> None:
        self.warnings.append(f"{self.display(path)}: {msg}")
        self.findings.append(("warning", self.display(path), msg))

    def display(self, path: Path) -> Path:
        return rel_to(path, self.root) if self.root else path

    def lines(self) -> list[str]:
        return [f"{WARN_PREFIX}{w}" for w in self.warnings] + [f"{ERROR_PREFIX}{e}" for e in self.errors]

    def annotations(self) -> list[str]:
        """The findings as GitHub Actions workflow commands, so a pull request shows each one on
        the file it names. Same order as `lines`; the message is otherwise unchanged."""
        return [
            f"::{level} file={path.as_posix()}::{msg.replace('%', '%25').replace(chr(10), '%0A')}"
            for level, path, msg in self.findings
        ]


def _outside_fences(text: str) -> Iterator[str]:
    """The lines of `text` not inside a fenced code block, fences themselves dropped.

    One implementation, so the link checker and the anchor collector cannot disagree about where
    code starts.
    """
    in_fence = False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            yield line


def headings(text: str) -> set[str]:
    """Heading anchors in GitHub's slug form, skipping fenced code blocks.

    Repeated headings are disambiguated the way GitHub does it, by suffixing the later ones with
    `-1`, `-2` and so on. Collapsing them made a *correct* link to the second `## Setup` report as
    a missing anchor -- an error, so valid markdown failed the build.
    """
    anchors: set[str] = set()
    seen: dict[str, int] = {}
    for line in _outside_fences(text):
        match = HEADING_RE.match(line)
        if match:
            slug = match.group(1).strip().lower()
            slug = re.sub(r"[^\w\s-]", "", slug)
            slug = re.sub(r"\s+", "-", slug)
            count = seen.get(slug, 0)
            seen[slug] = count + 1
            anchors.add(slug if count == 0 else f"{slug}-{count}")
    return anchors


def body_without_code(text: str) -> str:
    """Body with fenced blocks removed, so example links in code are not validated."""
    return "\n".join(_outside_fences(text))


def check_freshness(
    path: Path, updated: object, edited: set[Path] | None, settings: Settings, report: Report
) -> None:
    """`updated` names a real past date, and an edited note has had it bumped.

    The format check lives in `check_frontmatter`; this runs only once the field parses. A date in
    the future is an error -- nothing can have been edited then -- with a day of slack so a writer
    ahead of CI's UTC clock is not failed for it. Editing a note without bumping the date is the
    drift this whole convention exists to catch, but it is a warning: not every edit is
    substantive, and only a human can tell which was.
    """
    if not isinstance(updated, str) or not DATE_RE.match(updated):
        return
    try:
        stamp = date.fromisoformat(updated)
    except ValueError:
        report.error(path, f"'updated' is not a real date: {updated}")
        return
    today = date.today()
    if stamp > today + timedelta(days=settings.future_slack_days):
        report.error(path, f"'updated' is in the future: {updated}")
    elif edited is not None and path in edited and stamp != today:
        report.warn(
            path,
            f"edited by this change but 'updated' still reads {updated} "
            f"-- bump it to {today} if the edit was substantive",
        )


def check_prose(path: Path, prose: str, settings: Settings, report: Report) -> None:
    """The prose conventions a script can see. Everything else is a review obligation."""
    if not settings.em_dash:
        return
    hits = [
        number
        for number, line in enumerate(prose.splitlines(), start=1)
        if EM_DASH in INLINE_CODE_RE.sub("", line)
    ]
    if hits:
        report.warn(
            path,
            f"literal em dash on line(s) {', '.join(map(str, hits[:5]))}"
            f"{' and more' if len(hits) > 5 else ''} -- the convention writes it as ' -- '",
        )


def audit_assets(docs_root: Path, settings: Settings) -> list[tuple[Path, str]]:
    """Departures from the attachment-directory convention, as (path, message) pairs.

    Reported as warnings, never errors: `assets/` is not validated against. They exist so a
    misplaced file is visible rather than silently unchecked.
    """
    findings: list[tuple[Path, str]] = []
    assets = docs_root / settings.assets_dirname
    if assets.is_dir():
        for path in sorted(assets.rglob("*.md")):
            findings.append(
                (
                    path,
                    f"markdown under {settings.assets_dirname}/ -- that directory holds attachments "
                    "only, so this file is never validated or indexed",
                )
            )
    for path in sorted(docs_root.rglob(settings.assets_dirname)):
        if path.is_dir() and path.parent != docs_root:
            findings.append(
                (
                    path,
                    f"nested {settings.assets_dirname}/ -- attachments belong in the one "
                    f"{settings.assets_dirname}/ at the docs root, and this one is not exempt",
                )
            )
    return findings


def check_naming(path: Path, docs_root: Path, registry: Registry, report: Report) -> None:
    """Notes and the folders holding them match the filename pattern.

    A type may claim one exact filename instead and those are exempt. The exemption is read off the
    registry rather than granted to upper-case names generally, so a stray `NOTES.md` is still the
    naming error it was before.
    """
    settings = registry.settings
    rel = rel_to(path, docs_root)
    if path.name not in registry.fixed_names and not settings.name_re.match(path.stem):
        report.error(path, f"filename is not kebab-case: {path.name}")
    for part in rel.parts[:-1]:
        if not settings.name_re.match(part):
            report.error(path, f"folder is not kebab-case: {part}/")


def check_links(path: Path, body: str, repo_root: Path, report: Report) -> None:
    """Every link is a resolving relative path; wikilinks are not a link style here."""
    for raw in WIKILINK_RE.findall(body):
        report.error(path, f"wikilink -- use a relative markdown link instead: {raw}")

    own = headings(body)
    # Anchor sets of the files linked to, so a note with several links into one neighbour reads
    # and scans it once rather than once per link.
    neighbours: dict[Path, set[str]] = {}

    for target in LINK_RE.findall(body):
        if urlparse(target).scheme or target.startswith("//"):
            continue
        ref, _, anchor = target.partition("#")
        ref = unquote(ref)
        if not ref:
            if anchor and anchor.lower() not in own:
                report.error(path, f"link to missing local heading: #{anchor}")
            continue
        if ref.startswith("/"):
            report.error(path, f"absolute link path (use a relative one): {ref}")
            continue
        resolved = (path.parent / ref).resolve()
        if not resolved.exists():
            report.error(path, f"broken link: {target}")
            continue
        if anchor and resolved.suffix == ".md":
            found = neighbours.get(resolved)
            if found is None:
                found = neighbours[resolved] = headings(resolved.read_text(encoding="utf-8"))
            if anchor.lower() not in found:
                report.error(path, f"link anchor not found in {rel_to(resolved, repo_root)}: #{anchor}")


# --- anchors ------------------------------------------------------------------------------------

_KIND_ORDER = ("url", "docs-path", "repo-path", "opaque")


def describe_anchor(anchor: AnchorField, docs_root: Path, repo_root: Path) -> str:
    """What the field's entries may be, as prose for a message."""
    docs_prefix = rel_to(docs_root, repo_root)
    words = {
        "url": "URLs",
        "docs-path": f"repo-relative paths under {docs_prefix}/",
        "repo-path": "repo-relative paths",
        "opaque": "non-empty values",
    }
    return " or ".join(words[k] for k in _KIND_ORDER if k in anchor.resolves)


def resolve_entry(
    entry: str, anchor: AnchorField, docs_root: Path, repo_root: Path, registry: Registry
) -> str | None:
    """Why this entry fails the field's `resolves` kinds, or None when some kind accepts it.

    Every path in frontmatter is written from the repo root, never from the docs root and never
    absolute -- one path convention for every field. A `docs-path` that resolves outside the docs
    root is rejected on purpose: code belongs in a `repo-path` field, and accepting it here would
    let a note satisfy its anchor while staying off the drift spine.
    """
    kinds = anchor.resolves
    name = anchor.name
    if "opaque" in kinds and entry.strip():
        return None
    scheme = urlparse(entry).scheme
    if "url" in kinds and scheme in ("http", "https"):
        return None
    path_kinds = [k for k in ("docs-path", "repo-path") if k in kinds]
    if not path_kinds:
        return f"{name} must be an http(s) URL: {entry}"
    if Path(entry).is_absolute():
        return f"{name} must be repo-relative, not absolute: {entry}"
    resolved = (repo_root / entry).resolve()
    if "repo-path" in kinds and resolved.exists():
        return None
    if "docs-path" in kinds and resolved.is_relative_to(docs_root) and resolved.exists():
        return None
    if "repo-path" in kinds:
        return f"{name} path does not exist: {entry}"
    if not resolved.is_relative_to(docs_root):
        docs_prefix = rel_to(docs_root, repo_root)
        spine = " or ".join(registry.spine) or "a repo-path field"
        url_part = "a URL or " if "url" in kinds else ""
        return (
            f"{name} must be {url_part}a path under {docs_prefix}/ -- written from the repo root, "
            f"and code paths belong in {spine} instead: {entry}"
        )
    return f"{name} path does not exist (paths start at the repo root): {entry}"


def check_anchor(
    path: Path,
    anchor: AnchorField,
    entries: object,
    docs_root: Path,
    repo_root: Path,
    registry: Registry,
    report: Report,
) -> None:
    """A declared anchor field, whenever present, is a list whose every entry resolves by its kind."""
    if not isinstance(entries, list):
        report.error(
            path, f"'{anchor.name}' must be a list of {describe_anchor(anchor, docs_root, repo_root)}"
        )
        return
    for entry in entries:
        problem = resolve_entry(entry, anchor, docs_root, repo_root, registry)
        if problem is not None:
            report.error(path, problem)


def check_frontmatter(
    path: Path,
    meta: Meta,
    docs_root: Path,
    repo_root: Path,
    registry: Registry,
    report: Report,
) -> DocType | None:
    """Validate the frontmatter and return the note's type, or None if it does not name a live one."""
    settings = registry.settings
    doc_type = meta.get("type")
    spec = registry.get(doc_type)
    if spec is None:
        report.error(path, f"'type' must be one of {sorted(registry.enabled)}, got {doc_type!r}")

    updated = meta.get("updated")
    if not isinstance(updated, str) or not DATE_RE.match(updated):
        report.error(path, f"'updated' must be an ISO date (YYYY-MM-DD), got {updated!r}")

    summary = meta.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        report.error(path, "'summary' is required -- it is the only text the generated index shows")
    elif len(summary) > settings.summary_max:
        report.error(path, f"'summary' must be one short line (max {settings.summary_max} chars)")

    # Which anchors a type must carry is registry data: at least one of `requires`, and only from
    # the status `requires_from` names when it names one. Each field's own validation follows from
    # its `resolves` kinds and runs whenever the field is present, required or not.
    if spec is not None and spec.anchors_required(meta.get("status")):
        if not any(meta.get(name) for name in spec.requires):
            names = " or ".join(f"'{n}'" for n in spec.requires)
            since = f" once status is '{spec.requires_from}'" if spec.requires_from else ""
            what = "; ".join(f"{n}: {registry.anchor_fields[n].contents}" for n in spec.requires)
            report.error(path, f"type '{spec.name}' requires {names}{since} -- {what}")
    for name, anchor in registry.anchor_fields.items():
        if meta.get(name) is not None:
            check_anchor(path, anchor, meta[name], docs_root, repo_root, registry, report)

    if spec is None:
        return None

    status = meta.get("status")
    if spec.statuses and status not in spec.statuses:
        report.error(
            path, f"{spec.name} 'status' must be one of {sorted(spec.statuses)}, got {status!r}"
        )

    if spec.supersession is not None:
        rule = spec.supersession
        for key in (rule.forward, rule.back):
            other = meta.get(key)
            if isinstance(other, str) and not (path.parent / other).exists():
                report.error(path, f"'{key}' names a {spec.name} that does not exist: {other}")
        if status == rule.status and rule.back not in meta:
            report.error(path, f"status is '{rule.status}' but no '{rule.back}' is named")

    return spec


def check_lead(
    path: Path,
    spec: DocType,
    meta: Meta,
    registry: Registry,
    edited: set[Path] | None,
    changed: set[str] | None,
    report: Report,
) -> None:
    """A note anchored from a status onward was edited while none of the code it anchors to was.

    Such a note describes what is built, so an edit to it with no edit to the code means either a
    correction or the doc moving ahead of the code. Only the author knows which, and the second
    means the status is no longer true: the registry says which status precedes the anchored one,
    and the warning names it. Silent when git cannot say what changed.
    """
    if spec.requires_from is None or meta.get("status") != spec.requires_from:
        return
    if edited is None or changed is None or path not in edited:
        return
    refs = [
        str(ref)
        for name in registry.spine
        for ref in (meta.get(name) or [])
        if isinstance(ref, str)
    ]
    if not refs or any(matches(ref, changed) for ref in refs):
        return
    index = spec.statuses.index(spec.requires_from)
    before = f"'{spec.statuses[index - 1]}'" if index > 0 else "an earlier status"
    report.warn(
        path,
        f"edited while none of its code was ({', '.join(refs)}) -- if the doc now leads the code, "
        f"set status to {before} until the code catches up",
    )


def check_location(
    path: Path, spec: DocType, docs_root: Path, registry: Registry, report: Report
) -> None:
    """A type that names a folder, a numbering scheme or a filename is placed and named by it."""
    if spec.folder is not None and path.parent != docs_root / spec.folder:
        where = rel_to(path.parent, docs_root)
        report.error(path, f"a '{spec.name}' note belongs in {spec.folder}/, not {where}/")
    if spec.numbered and not registry.settings.numbered_name_re.match(path.stem):
        report.error(path, f"a '{spec.name}' filename must be NNNN-kebab-slug.md")

    # A claimed filename binds in both directions. One way alone leaves a hole: a `context` note
    # under another name is unfindable by the checks that glob for it, and any other type wearing
    # the name would be picked up by them and parsed as something it is not.
    if spec.fixed_name is not None and path.name != spec.fixed_name:
        report.error(path, f"a '{spec.name}' note must be named {spec.fixed_name}")
    owner = registry.fixed_names.get(path.name)
    if owner is not None and owner != spec.name:
        report.error(
            path, f"{path.name} is the '{owner}' type's filename, but this declares '{spec.name}'"
        )


# --- structure ----------------------------------------------------------------------------------

SECTION_RE = re.compile(r"^##\s+(.*)$")
# A markdown table row: at least one pipe-delimited cell between outer pipes.
TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?$")
# Cells naming nothing. A structured table says "no aliases" with a dash rather than a blank,
# because a blank cell reads as an unfinished row.
EMPTY_CELLS = frozenset({"", "-", "--", "n/a", "none"})


def _cells(line: str) -> list[str]:
    """The cells of a markdown table row, outer pipes dropped."""
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def sections_of(prose: str) -> list[str]:
    """The `##` headings of a note, in document order. Fences are already stripped."""
    return [match.group(1).strip() for line in prose.splitlines() if (match := SECTION_RE.match(line))]


def parse_table(prose: str, structure: Structure) -> tuple[list[str], list[list[str]]]:
    """The header and body rows of the table under `structure.table_in`.

    Returns empty lists when the section or its table is absent; reporting that is
    `check_structure`'s job, and every caller wants the same tolerant read.
    """
    lines = prose.splitlines()
    start = next(
        (
            i
            for i, line in enumerate(lines)
            if (match := SECTION_RE.match(line)) and match.group(1).strip() == structure.table_in
        ),
        None,
    )
    if start is None:
        return [], []
    header: list[str] = []
    rows: list[list[str]] = []
    for line in lines[start + 1 :]:
        if SECTION_RE.match(line):
            break
        if not TABLE_ROW_RE.match(line):
            continue
        cells = _cells(line)
        if not header:
            header = cells
        elif all(SEPARATOR_CELL_RE.match(cell) for cell in cells):
            continue
        else:
            rows.append(cells)
    return header, rows


def check_structure(path: Path, spec: DocType, prose: str, text: str, report: Report) -> None:
    """A type whose body is data is validated for shape, not just for prose.

    Every one of these is an error rather than a warning. The shape is what other checks parse: a
    renamed column or a dropped section does not degrade them, it silently turns them off, and a
    check that has quietly stopped running is worse than one that never existed.

    `text` is the whole file as read by the caller: the size cap is on the note as emitted,
    frontmatter included.
    """
    structure = spec.structure
    if structure is None:
        return

    found = sections_of(prose)
    if tuple(found) != structure.sections:
        report.error(
            path,
            f"a '{spec.name}' note's sections must be exactly "
            f"{', '.join('## ' + s for s in structure.sections)} in that order, got "
            f"{', '.join('## ' + s for s in found) or 'none'}",
        )

    size = len(text)
    if size > structure.max_chars:
        report.error(
            path,
            f"{size} chars -- a '{spec.name}' note is emitted into every session and is capped at "
            f"{structure.max_chars}; cut terms or tighten definitions",
        )

    header, rows = parse_table(prose, structure)
    if tuple(header) != structure.columns:
        report.error(
            path,
            f"the table under '## {structure.table_in}' must have exactly the columns "
            f"{' | '.join(structure.columns)}, got {' | '.join(header) or 'no table'}",
        )
        return

    if len(rows) > structure.max_rows:
        report.error(
            path,
            f"{len(rows)} rows under '## {structure.table_in}' -- capped at {structure.max_rows}; "
            "a term that no longer earns its place comes out before a new one goes in",
        )

    index = {name: position for position, name in enumerate(header)}
    for row in rows:
        if len(row) != len(header):
            report.error(path, f"table row has {len(row)} cells, expected {len(header)}: {row}")
            continue
        key = row[index[structure.key_column]]
        body = row[index[structure.body_column]]
        if key.strip().strip("*`") == "":
            report.error(path, f"table row with an empty '{structure.key_column}': {row}")
        if len(body) > structure.max_cell:
            report.error(
                path, f"'{key}' definition is {len(body)} chars -- one line, max {structure.max_cell}"
            )


# --- vocabulary ---------------------------------------------------------------------------------


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
    header, rows = parse_table(body_without_code(body), structure)
    if tuple(header) != structure.columns:
        return {}
    index = {name: position for position, name in enumerate(header)}
    terms: dict[str, list[str]] = {}
    for row in rows:
        if len(row) != len(header):
            continue
        key = row[index[structure.key_column]].strip().strip("*`")
        if not key:
            continue
        aliases: list[str] = []
        for column in structure.scanned_columns:
            cell = row[index[column]]
            if cell.strip().lower() in EMPTY_CELLS:
                continue
            aliases += [
                alias.strip().strip("*`") for alias in cell.split(",") if alias.strip().strip("*`")
            ]
        terms[key] = aliases
    return terms


@dataclass
class Vocabulary:
    """The terms in force under each directory that holds a structured, fixed-name note.

    Resolution is by containment rather than by exact directory, so a note deep in the tree
    inherits every context note above it. `additive` is what makes merging them safe: no two
    context notes in one chain may define the same term, so the merge cannot depend on order.
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


def build_vocabulary(
    docs_root: Path, registry: Registry, report: Report, in_scope: set[Path] | None
) -> Vocabulary:
    """Collect every context note's terms, reporting collisions down each chain.

    A nested note redefining an ancestor's term is an error: the point of the file is that one word
    has one meaning, and a repo where the meaning depends on which directory you are reading from
    has reintroduced exactly the ambiguity the vocabulary exists to remove.
    """
    vocabulary = Vocabulary()
    for spec in registry.enabled.values():
        if spec.structure is None or spec.fixed_name is None:
            continue
        notes = {
            path: read_terms(path, spec)
            for path in iter_named(docs_root, spec.fixed_name, registry.settings)
        }
        for path, terms in notes.items():
            vocabulary.by_dir[path.parent] = terms
            if not spec.additive:
                continue
            for other, ancestor_terms in notes.items():
                if other.parent == path.parent or not path.parent.is_relative_to(other.parent):
                    continue
                for term in sorted(set(terms) & set(ancestor_terms)):
                    if in_scope is None or path in in_scope:
                        report.error(
                            path,
                            f"'{term}' is already defined by {rel_to(other, docs_root)} -- a "
                            f"nested '{spec.name}' note adds terms, it never redefines them",
                        )
    return vocabulary


def alias_re(alias: str) -> re.Pattern[str]:
    """A whole-word match for an alias, robust to aliases that start or end in a non-word character.

    `\\b` misbehaves there: `\\b.env\\b` needs a word character right before the dot, so `.env` at
    the start of a sentence never matches, and `C++` can never end at a word boundary. Lookarounds
    ask the right question -- not touching a word character on either side -- for every alias. An
    alias whose edge is itself punctuation must also not touch a repeat of that character, so
    `C+++` and `..env` are not sightings of `C++` and `.env`.
    """

    def edge(char: str) -> str:
        return r"\w" if re.match(r"\w", char) else rf"\w{re.escape(char)}"

    return re.compile(rf"(?<![{edge(alias[0])}]){re.escape(alias)}(?![{edge(alias[-1])}])", re.IGNORECASE)


def check_vocabulary(
    path: Path, spec: DocType | None, prose: str, vocabulary: Vocabulary, report: Report
) -> None:
    """Prose uses the vocabulary's terms rather than the aliases it rules out.

    A warning, not an error: the scan is a word match and cannot see intent, and a false positive
    that blocks a commit would be worse than the drift it catches.

    Two exemptions, both structural. An append-only type is skipped because its wording cannot
    lawfully be corrected. Code spans and fenced blocks are skipped because a banned alias is
    routinely the literal name of a field or an API, and backticks are how you say so.
    """
    if spec is None or spec.append_only or spec.structure is not None:
        return
    banned = vocabulary.aliases_for(path)
    if not banned:
        return
    text = INLINE_CODE_RE.sub("", prose)
    for alias in sorted(banned):
        if alias_re(alias).search(text):
            report.warn(
                path,
                f"'{alias}' is an alias the vocabulary rules out -- use "
                f"'{banned[alias]}' instead, or put it in backticks if it is a literal name",
            )


# --- per-note and tree-wide ----------------------------------------------------------------------


def check_doc(
    path: Path,
    docs_root: Path,
    repo_root: Path,
    registry: Registry,
    report: Report,
    edited: set[Path] | None,
    changed: set[str] | None,
    vocabulary: Vocabulary,
) -> None:
    meta, body, text, error = read_note(path)
    spec: DocType | None = None

    check_naming(path, docs_root, registry, report)

    if error is not None:
        report.error(path, error)
    else:
        assert meta is not None  # read_note returns one or the other
        spec = check_frontmatter(path, meta, docs_root, repo_root, registry, report)
        if spec is not None:
            check_location(path, spec, docs_root, registry, report)
            check_lead(path, spec, meta, registry, edited, changed, report)
        check_freshness(path, meta.get("updated"), edited, registry.settings, report)

    prose = body_without_code(body)
    if spec is not None:
        check_structure(path, spec, prose, text, report)
    check_prose(path, prose, registry.settings, report)
    check_vocabulary(path, spec, prose, vocabulary, report)
    check_links(path, prose, repo_root, report)


def check_required_notes(
    docs_root: Path, repo_root: Path, registry: Registry, report: Report, in_scope: set[Path] | None
) -> None:
    """A type the registry marks `root_required` has an instance at the docs root.

    Scoped like `check_numbering`: a run that touched one reference note should not fail on a file
    it never opened. A sweep reports it, and so does a run that names the missing file itself.
    """
    for spec in registry.enabled.values():
        if not spec.root_required or spec.fixed_name is None:
            continue
        target = docs_root / spec.fixed_name
        if target.is_file():
            continue
        if in_scope is not None and not any(p.name == spec.fixed_name for p in in_scope):
            continue
        report.error(
            target,
            f"missing -- every docs root carries a '{spec.name}' note at "
            f"{rel_to(docs_root, repo_root)}/{spec.fixed_name}",
        )


def check_numbering(
    docs_root: Path, registry: Registry, report: Report, in_scope: set[Path] | None
) -> None:
    """Within each numbered type's folder, numbers are unique.

    `in_scope` limits which collisions are reported: a run that touched one reference doc should
    not fail on two decision files it never opened. None reports every collision.
    """
    for spec in registry.enabled.values():
        if not spec.numbered or spec.folder is None:
            continue
        folder = docs_root / spec.folder
        if not folder.is_dir():
            continue
        if in_scope is not None and not any(p.parent == folder for p in in_scope):
            continue
        seen: dict[str, Path] = {}
        for path in sorted(folder.glob("*.md")):
            match = registry.settings.numbered_name_re.match(path.stem)
            if not match:
                continue
            number = match.group(1)
            other = seen.get(number)
            if other is None:
                seen[number] = path
                continue
            if in_scope is None or {path, other} & in_scope:
                report.error(path, f"duplicate {spec.name} number {number} (also {other.name})")


def run(
    docs_root: Path,
    registry: Registry,
    targets: list[Path],
    *,
    sweep: bool,
    rev_range: str | None = None,
    skip_non_notes: bool = False,
) -> tuple[Report, int]:
    """Validate `targets` (or the whole tree with `sweep`). Returns the report and the count checked."""
    settings = registry.settings
    repo_root = find_repo_root(docs_root)
    # Which notes the change touched, so an unbumped `updated` is reportable: the working tree by
    # default, or an explicit range where there is no working tree to read. None when git cannot
    # say -- "cannot tell" is not "nothing edited", and the check stays quiet.
    edited = edited_notes(repo_root, rev_range, docs_root)
    # What the same change touched outside the docs, for the notes whose status claims to match
    # the code. Read only when some note was edited, so a clean tree costs no extra git call.
    changed = changed_paths(repo_root, rev_range) if edited else None

    report = Report(root=repo_root)
    in_scope = None if sweep else set(targets)
    # Built once, from the whole tree rather than from the run's targets: a note being checked
    # inherits the vocabulary of every context note above it, most of which this run never names.
    vocabulary = build_vocabulary(docs_root, registry, report, in_scope)
    checked = 0
    for path in targets:
        if not path.is_file():
            if skip_non_notes:
                continue
            report.error(path, "not a file")
            continue
        if not path.is_relative_to(docs_root):
            if skip_non_notes:
                continue
            report.error(path, f"outside the docs root ({docs_root}) -- wrong --docs-root?")
            continue
        if not is_checkable(path, docs_root, settings):
            continue
        if classify(path, docs_root, settings) == FORBIDDEN:
            report.error(
                path,
                f"{path.name} does not belong under {docs_root.name}/ "
                f"-- {settings.forbidden_names[path.name]}",
            )
            checked += 1
            continue
        check_doc(path, docs_root, repo_root, registry, report, edited, changed, vocabulary)
        checked += 1

    check_required_notes(docs_root, repo_root, registry, report, in_scope)
    check_numbering(docs_root, registry, report, in_scope)

    if sweep:
        for path, message in audit_assets(docs_root, settings):
            report.warn(path, message)
    return report, checked


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="doc-marshal check",
        description="Validate notes against the registry. Exits 1 on any error; warnings never fail.",
    )
    parser.add_argument("paths", nargs="*", type=Path, help="notes to check")
    parser.add_argument(
        "--all", action="store_true", help="sweep every note under the docs root (what CI runs)"
    )
    parser.add_argument(
        "--range",
        help="git range whose notes count as edited, e.g. main..HEAD (default: the working tree; "
        "CI has no working-tree changes and must pass this to check freshness at all)",
    )
    parser.add_argument(
        "--skip-non-notes",
        action="store_true",
        help="silently skip paths that are not notes under the docs root, and exit 0 when there is "
        "no docs root at all -- for hooks handed every file a change touched",
    )
    parser.add_argument(
        "--format",
        choices=("text", "github"),
        default="text",
        help="github: one workflow command per finding, so a pull request shows it on the file",
    )
    parser.add_argument("--docs-root", help="docs root (default: the directory holding the marker)")
    args = parser.parse_args(argv)

    if not args.all and not args.paths:
        parser.error("name the notes to check, or pass --all")

    try:
        docs_root = find_docs_root(args.docs_root)
    except DocMarshalError:
        if args.skip_non_notes:
            return 0
        raise
    registry = load_registry(docs_root)

    targets = iter_checkable(docs_root, registry.settings) if args.all else [p.resolve() for p in args.paths]
    report, checked = run(
        docs_root,
        registry,
        targets,
        sweep=args.all,
        rev_range=args.range,
        skip_non_notes=args.skip_non_notes,
    )

    for line in report.annotations() if args.format == "github" else report.lines():
        print(line)
    if checked or not args.skip_non_notes:
        print(
            f"\n{checked} note(s) checked -- {len(report.errors)} error(s), {len(report.warnings)} warning(s)"
        )
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
