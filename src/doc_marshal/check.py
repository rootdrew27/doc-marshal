"""`doc-marshal check`: validate notes against the registry -- naming, frontmatter, anchors, links,
location, structure, vocabulary.

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
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import cached_property
from pathlib import Path
from urllib.parse import unquote, urlparse

from .affected import matches
from .anchors import check_anchor
from .config import add_docs_root_option, load_registry
from .index import plural
from .markdown import (
    body_without_code,
    cell_items,
    cell_text,
    heading_lines,
    headings,
    parse_table,
    sections,
    strip_comments,
    table_chars,
    without_code_spans,
)
from .ontology import DocType, Registry
from .paths import (
    FORBIDDEN,
    DocMarshalError,
    Meta,
    anchor_entries,
    change_start,
    changed_paths,
    classify,
    edited_notes,
    exists_exact,
    find_docs_root,
    find_repo_root,
    is_checkable,
    iter_checkable,
    read_note,
    rel_to,
    validate_range,
)
from .report import Report
from .settings import NOTE_SUFFIX, NUMBER_PREFIX_RE, NUMBER_TITLE_SEPARATOR, Settings
from .vocabulary import Vocabulary, build_vocabulary, check_vocabulary

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# A link or an image: the destination is either `<...>` (CommonMark's spelling for a destination
# holding spaces) or a run without spaces or a closing paren.
LINK_RE = re.compile(r"\[[^\]]*\]\((?:<([^>]+)>|([^)\s]+))\)")
WIKILINK_RE = re.compile(r"\[\[[^\]]+\]\]")


@dataclass
class Scope:
    """What one run knows once, handed to every per-note check.

    The git facts are read on first use and never twice: which notes the change touched, for the
    freshness check on every note; what it touched outside the docs and the day it began, which
    only a note that gets past the cheaper tests ever asks for. None from any of them means git
    could not say -- "cannot tell" is not "nothing edited", and the checks stay quiet.
    """

    docs_root: Path
    repo_root: Path
    registry: Registry
    rev_range: str | None = None
    vocabulary: Vocabulary = field(default_factory=Vocabulary)
    headings_of: dict[Path, set[str]] = field(default_factory=dict)  # linked notes, read once

    @cached_property
    def edited(self) -> set[Path] | None:
        return edited_notes(self.repo_root, self.rev_range, self.docs_root)

    @cached_property
    def changed(self) -> set[str]:
        return changed_paths(self.repo_root, self.rev_range)

    @cached_property
    def since(self) -> date | None:
        return change_start(self.repo_root, self.rev_range)

    def touched(self, path: Path) -> bool:
        """Whether the change edited this note, as far as git can tell."""
        return self.edited is not None and path in self.edited


def check_freshness(path: Path, updated: object, scope: Scope, report: Report) -> None:
    """`updated` names a real past date, and an edited note has had it bumped.

    The format check lives in `check_frontmatter`; this runs only once the field parses. A date in
    the future is an error -- nothing can have been edited then -- with a day of slack so a writer
    ahead of CI's UTC clock is not failed for it.

    An edited note's date must be no earlier than the day the change began: today for a
    working-tree run, the earliest commit's day for a range. That makes the rule purely mechanical
    -- a note dated the day it was edited stays valid however long its pull request takes -- and
    so it is an error. Silent when git could not say what was edited or when.
    """
    if not isinstance(updated, str) or not DATE_RE.match(updated):
        return
    try:
        stamp = date.fromisoformat(updated)
    except ValueError:
        report.error(path, f"'updated' is not a real date: {updated}")
        return
    today = date.today()
    if stamp > today + timedelta(days=scope.registry.settings.future_slack_days):
        report.error(path, f"'updated' is in the future: {updated}")
        return
    if not scope.touched(path) or scope.since is None or stamp >= scope.since:
        return
    window = f" (the change began on {scope.since})" if scope.since != today else ""
    report.error(path, f"edited by this change but 'updated' still reads {updated} -- bump it to {today}{window}")


def audit_assets(docs_root: Path, settings: Settings, report: Report) -> None:
    """Departures from the attachment-directory convention.

    Errors, like every rule about shape: a markdown file under `assets/` is never validated or
    indexed, and a nested `assets/` is not exempt, so either is a file the tree has quietly
    stopped governing. Only a sweep reports them -- they are facts about the tree, not a note.
    """
    assets = docs_root / settings.assets_dirname
    if assets.is_dir():
        for path in sorted(assets.rglob(f"*{NOTE_SUFFIX}")):
            report.error(
                path,
                f"markdown under {settings.assets_dirname}/ -- that directory holds attachments "
                "only, so this file is never validated or indexed",
            )
    for path in sorted(docs_root.rglob(settings.assets_dirname)):
        if path.is_dir() and path.parent != docs_root:
            report.error(
                path,
                f"nested {settings.assets_dirname}/ -- attachments belong in the one "
                f"{settings.assets_dirname}/ at the docs root, and this one is not exempt",
            )


def check_naming(path: Path, docs_root: Path, registry: Registry, report: Report) -> None:
    """Notes and the folders holding them match the filename pattern.

    A type may claim one exact filename instead and those are exempt. The exemption is read off the
    registry rather than granted to upper-case names generally, so a stray `NOTES.md` is still the
    naming error it was before.
    """
    settings = registry.settings
    if path.name not in registry.fixed_names and not settings.name_re.match(path.stem):
        report.error(path, f"filename is not kebab-case: {path.name}")
    for part in rel_to(path, docs_root).parts[:-1]:
        if not settings.name_re.match(part):
            report.error(path, f"folder is not kebab-case: {part}/")


def check_links(path: Path, prose: str, scan: str, scope: Scope, report: Report) -> None:
    """Every link and image is a resolving relative path; wikilinks are not a link style here.

    A target is resolved with exact spelling and must stay inside the repository: a link that
    leaves it is broken for every clone but this one. Links are read from `scan`, the prose with
    its code spans removed, the way the alias scan reads it: backticks are how a note quotes a
    link rather than makes one. The note's own headings are read from `prose`, spans intact,
    because a backtick in a heading is part of its slug. A heading anchor must match the slug
    GitHub would make, case included, because that is the resolver a reader's click goes
    through. A linked note's headings are read once per run, however many notes link into it.
    """
    for raw in WIKILINK_RE.findall(scan):
        report.error(path, f"wikilink -- use a relative markdown link instead: {raw}")

    own = headings(prose)
    for bracketed, bare in LINK_RE.findall(scan):
        target = bracketed or bare
        if urlparse(target).scheme or target.startswith("//"):
            continue
        ref, _, anchor = target.partition("#")
        ref = unquote(ref)
        if not ref:
            if anchor and anchor not in own:
                report.error(path, f"link to missing local heading: #{anchor}")
            continue
        if ref.startswith("/"):
            report.error(path, f"absolute link path (use a relative one): {ref}")
            continue
        resolved = (path.parent / ref).resolve()
        if not exists_exact(scope.repo_root, resolved):
            report.error(path, f"broken link: {target}")
            continue
        if anchor and resolved.suffix == NOTE_SUFFIX:
            found = scope.headings_of.get(resolved)
            if found is None:
                found = scope.headings_of[resolved] = headings(resolved.read_text(encoding="utf-8"))
            if anchor not in found:
                report.error(path, f"link anchor not found in {rel_to(resolved, scope.repo_root)}: #{anchor}")


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

    status = meta.get("status")
    # Which anchors a type must carry is registry data: at least one of `requires`, and only from
    # the status `requires_from` names when it names one. Each field's own validation follows from
    # its `resolves` kinds and runs whenever the field is present, required or not.
    if spec is not None and spec.anchors_required(status) and not any(meta.get(n) for n in spec.requires):
        names = " or ".join(f"'{n}'" for n in spec.requires)
        since = f" once status is '{spec.requires_from}'" if spec.requires_from else ""
        what = "; ".join(f"{n}: {registry.anchor_fields[n].contents}" for n in spec.requires)
        report.error(path, f"type '{spec.name}' requires {names}{since} -- {what}")
    for name, anchor in registry.anchor_fields.items():
        if meta.get(name) is not None:
            check_anchor(path, anchor, meta[name], docs_root, repo_root, registry, report)

    if spec is None:
        return None

    if spec.statuses and status not in spec.statuses:
        report.error(path, f"{spec.name} 'status' must be one of {sorted(spec.statuses)}, got {status!r}")

    if spec.supersession is not None:
        rule = spec.supersession
        for key in (rule.forward, rule.back):
            other = meta.get(key)
            if not isinstance(other, str):
                continue
            target = (path.parent / other).resolve()
            if target == path:
                report.error(path, f"'{key}' names this note itself: {other}")
            elif not exists_exact(repo_root, target):
                report.error(path, f"'{key}' names a {spec.name} that does not exist: {other}")
        if status == rule.status and rule.back not in meta:
            report.error(path, f"status is '{rule.status}' but no '{rule.back}' is named")
        if rule.back in meta and status != rule.status:
            report.error(
                path,
                f"'{rule.back}' is named but status is {status!r} -- a replaced {spec.name} says "
                f"'status: {rule.status}'",
            )

    # A key the type does not declare is a typo or a private convention, and both used to pass
    # unread: `code-refs` anchored nothing and validated as if it had. The set is the registry's,
    # so a declared anchor field is legal on every type and a status only where the type has one.
    known = registry.frontmatter_keys(spec)
    for key in meta:
        if key not in known:
            report.error(
                path,
                f"unknown frontmatter key '{key}' -- a '{spec.name}' note may carry {', '.join(known)}",
            )

    return spec


def check_title(path: Path, spec: DocType | None, body: str, report: Report) -> None:
    """One H1, first, and for a numbered note carrying the number its filename does.

    A note without a title has nothing for a reader or an index to call it; a second H1 is two
    notes in one file. The number in the title is what `new` writes, and the filename is the
    source of truth for it, so the two drifting apart is caught here rather than read as a
    typo. Read outside fences, where a `# comment` is code.
    """
    levels = list(heading_lines(body))
    titles = [text for level, text in levels if level == 1]
    if not titles:
        report.error(path, "no title -- the first heading is a single H1 naming the note")
        return
    if levels[0][0] != 1:
        report.error(path, f"the first heading must be the H1 title, not '{'#' * levels[0][0]} {levels[0][1]}'")
    if len(titles) > 1:
        report.error(path, f"{len(titles)} H1 headings -- one note is one file; the second is '{titles[1]}'")
    if spec is None or not spec.numbered:
        return
    number = NUMBER_PREFIX_RE.match(path.stem)
    if number is not None and not titles[0].startswith(number.group(1) + NUMBER_TITLE_SEPARATOR):
        report.error(
            path,
            f"a '{spec.name}' title starts with its number: "
            f"'{number.group(1)}{NUMBER_TITLE_SEPARATOR}...', got '{titles[0]}'",
        )


def check_sections(path: Path, spec: DocType, meta: Meta, body: str, report: Report) -> None:
    """A prose type's required sections are present, once each, in order, and say something.

    The skeleton wrote every one of these, so a missing section was deleted and an empty one was
    never written; both are what `check` exists to catch before a reader does. Other sections are
    the author's. Comments were stripped by the caller, so a section holding only its scaffold
    comment is blank. A section the type wants empty from a status onward is the reverse check:
    a `done` spec with an open question is not done.
    """
    found = sections(body)
    names = [name for name, _ in found]
    spine = ", ".join(f"## {s}" for s in spec.required_sections)
    positions: list[int] = []
    for name in spec.required_sections:
        count = names.count(name)
        if count == 0:
            report.error(path, f"missing '## {name}' -- a '{spec.name}' note carries {spine}, in that order")
            continue
        if count > 1:
            report.error(path, f"'## {name}' appears {count} times -- a required section appears once")
        index = names.index(name)
        positions.append(index)
        if not "\n".join(found[index][1]).strip():
            report.error(path, f"'## {name}' is empty -- a required section says something, even in one line")
    if positions != sorted(positions):
        order = ", ".join(f"## {s}" for s in names if s in spec.required_sections)
        report.error(path, f"sections out of order: got {order}; a '{spec.name}' note carries {spine}")
    for section, status in spec.empty_at:
        if meta.get("status") != status:
            continue
        for name, lines in found:
            if name == section and "\n".join(lines).strip():
                report.error(
                    path,
                    f"status is '{status}' but '## {section}' still has content -- resolve each "
                    f"item, or the status is not yet true",
                )


def check_lead(path: Path, spec: DocType, meta: Meta, scope: Scope, report: Report) -> None:
    """A note anchored from a status onward was edited while none of the code it anchors to was.

    Such a note describes what is built, so an edit to it with no edit to the code means either a
    correction or the doc moving ahead of the code. Only the author knows which, and the second
    means the status is no longer true: the registry says which status precedes the anchored one,
    and the warning names it. Silent when git cannot say what changed.
    """
    if spec.requires_from is None or meta.get("status") != spec.requires_from or not scope.touched(path):
        return
    refs = [ref for name in scope.registry.spine for ref in anchor_entries(meta, name)]
    if not refs or any(matches(ref, scope.changed) for ref in refs):
        return
    index = spec.statuses.index(spec.requires_from)
    before = f"'{spec.statuses[index - 1]}'" if index > 0 else "an earlier status"
    report.warn(
        path,
        f"edited while none of its code was ({', '.join(refs)}) -- if the doc now leads the code, "
        f"set status to {before} until the code catches up",
    )


def check_location(path: Path, spec: DocType, docs_root: Path, registry: Registry, report: Report) -> None:
    """A type that names a folder, a numbering scheme or a filename is placed and named by it."""
    if spec.folder is not None and path.parent != spec.home(docs_root):
        where = rel_to(path.parent, docs_root)
        report.error(path, f"a '{spec.name}' note belongs in {spec.folder}/, not {where}/")
    if spec.numbered and not registry.settings.numbered_name_re.match(path.stem):
        report.error(path, f"a '{spec.name}' filename must be NNNN-kebab-slug.md")

    # A claimed filename binds in both directions. One way alone leaves a hole: a `nomenclature` note
    # under another name is unfindable by the checks that glob for it, and any other type wearing
    # the name would be picked up by them and parsed as something it is not.
    if spec.fixed_name is not None and path.name != spec.fixed_name:
        report.error(path, f"a '{spec.name}' note must be named {spec.fixed_name}")
    owner = registry.fixed_names.get(path.name)
    if owner is not None and owner != spec.name:
        report.error(path, f"{path.name} is the '{owner}' type's filename, but this declares '{spec.name}'")


def check_structure(path: Path, spec: DocType, prose: str, body: str, report: Report) -> None:
    """A type whose body is data is validated for shape, not just for prose.

    Every one of these is an error rather than a warning. The shape is what other checks parse: a
    renamed column or a dropped section does not degrade them, it silently turns them off, and a
    check that has quietly stopped running is worse than one that never existed.

    `body` is the note below its frontmatter. `max_chars` is measured on it with the table's rows
    taken out: the rows are `max_rows`' business, the prose around them is this cap's, and the
    frontmatter is neither -- a session never sees it.

    Keys are compared case-insensitively: `Widget` and `widget` are one term twice, and an alias
    that is also a term rules out the word the table defines.
    """
    structure = spec.structure
    if structure is None:
        return

    found = [name for name, _ in sections(prose)]
    if tuple(found) != structure.sections:
        report.error(
            path,
            f"a '{spec.name}' note's sections must be exactly "
            f"{', '.join('## ' + s for s in structure.sections)} in that order, got "
            f"{', '.join('## ' + s for s in found) or 'none'}",
        )

    outside = len(body) - table_chars(body, structure.table_in)
    if outside > structure.max_chars:
        report.error(
            path,
            f"{outside} chars in the body outside the '{structure.table_in}' table -- a "
            f"'{spec.name}' note is emitted into every session; the prose around its table is "
            f"capped at {structure.max_chars} (the table at {structure.max_rows} rows)",
        )

    header, rows, malformed = parse_table(prose, structure.table_in)
    if not structure.accepts(header):
        report.error(
            path,
            f"the table under '## {structure.table_in}' must have exactly the columns "
            f"{' | '.join(structure.columns)}, got {' | '.join(header) or 'no table'}",
        )
        return

    if len(rows) + len(malformed) > structure.max_rows:
        report.error(
            path,
            f"{len(rows) + len(malformed)} rows under '## {structure.table_in}' -- capped at "
            f"{structure.max_rows}; a term that no longer earns its place comes out before a new one goes in",
        )

    for cells in malformed:
        report.error(path, f"table row has {len(cells)} cells, expected {len(header)}: {cells}")
    keys: dict[str, str] = {}
    for row in rows:
        key = cell_text(row[structure.key_column])
        definition = row[structure.body_column]
        if not key:
            report.error(path, f"table row with an empty '{structure.key_column}': {list(row.values())}")
        elif key.lower() in keys:
            report.error(path, f"'{key}' is defined twice (also as '{keys[key.lower()]}') -- one row per term")
        else:
            keys[key.lower()] = key
        if len(definition) > structure.max_cell:
            report.error(path, f"'{key}' definition is {len(definition)} chars -- one line, max {structure.max_cell}")
    for row in rows:
        for column in structure.scanned_columns:
            for alias in cell_items(row[column]):
                if alias.lower() in keys:
                    report.error(
                        path,
                        f"'{alias}' is listed under '{column}' but is also the term '{keys[alias.lower()]}' "
                        "-- a word is defined or ruled out, not both",
                    )


# --- per-note and tree-wide ----------------------------------------------------------------------


def check_doc(path: Path, scope: Scope, report: Report) -> None:
    docs_root, repo_root, registry = scope.docs_root, scope.repo_root, scope.registry
    meta, body, _, error = read_note(path)
    spec: DocType | None = None

    check_naming(path, docs_root, registry, report)

    if error is not None:
        report.error(path, error)
    else:
        assert meta is not None  # read_note returns one or the other
        spec = check_frontmatter(path, meta, docs_root, repo_root, registry, report)
        if spec is not None:
            check_location(path, spec, docs_root, registry, report)
            check_lead(path, spec, meta, scope, report)
        check_freshness(path, meta.get("updated"), scope, report)

    # Three views of the body, each computed once. Comments come out first, so a comment spanning
    # two headings hides the second the way markdown renders it and a section holding only its
    # scaffold comment is blank; then fenced blocks, which are content but not prose; then code
    # spans, which quote a name rather than use it. The raw body still measures the size cap.
    plain = strip_comments(body)
    prose = body_without_code(plain)
    scan = without_code_spans(prose)
    check_title(path, spec, plain, report)
    if spec is not None:
        assert meta is not None  # a resolved type came from parsed frontmatter
        check_sections(path, spec, meta, plain, report)
        check_structure(path, spec, prose, body, report)
        check_vocabulary(path, spec, meta, scan, scope.vocabulary, report)
    check_links(path, prose, scan, scope, report)


def check_required_notes(
    docs_root: Path, repo_root: Path, registry: Registry, report: Report, in_scope: set[Path] | None
) -> None:
    """A type the registry marks `root_required` has an instance at the docs root.

    Scoped like `check_numbering`: a run that touched one reference note should not fail on a file
    it never opened. A sweep reports it, and so does a run that names the missing file itself.
    """
    for spec in registry.root_notes:
        target = spec.fixed_path(docs_root)
        if exists_exact(repo_root, target):
            continue
        if in_scope is not None and not any(p.name == spec.fixed_name for p in in_scope):
            continue
        report.error(
            target,
            f"missing -- every docs root carries a '{spec.name}' note at "
            f"{rel_to(docs_root, repo_root)}/{spec.fixed_name}",
        )


def check_numbering(docs_root: Path, registry: Registry, report: Report, in_scope: set[Path] | None) -> None:
    """Within each numbered type's folder, numbers are unique.

    `in_scope` limits which collisions are reported: a run that touched one reference doc should
    not fail on two decision files it never opened. None reports every collision.
    """
    for spec in registry.enabled.values():
        if not spec.numbered:
            continue
        folder = spec.home(docs_root)
        if not folder.is_dir():
            continue
        if in_scope is not None and not any(p.parent == folder for p in in_scope):
            continue
        seen: dict[str, Path] = {}
        for path in sorted(folder.glob(f"*{NOTE_SUFFIX}")):
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


def unchecked_reason(path: Path, docs_root: Path, settings: Settings) -> str | None:
    """Why a named path is nothing the validator governs, or None when it is a note to check.

    A hook handed every file a change touched asks to skip these; anyone else naming one is told,
    because a run that checked nothing and reported clean is the worst answer it could give.
    """
    if not path.is_file():
        return "not a file"
    if not path.is_relative_to(docs_root):
        return f"outside the docs root ({docs_root}) -- wrong --docs-root?"
    if not is_checkable(path, docs_root, settings):
        return (
            f"not a note ({classify(path, docs_root, settings)}) -- generated, agent-memory, "
            "tooling and attachment files are never validated"
        )
    return None


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
    if rev_range:
        validate_range(repo_root, rev_range)
    report = Report(root=repo_root)

    to_check: list[Path] = []
    for path in targets:
        why = unchecked_reason(path, docs_root, settings)
        if why is None:
            to_check.append(path)
        elif not skip_non_notes:
            report.error(path, why)

    # Everything git and the tree are asked is asked after the targets are sorted, so a hook
    # handed a markdown file that is not a note pays for nothing.
    scope = Scope(docs_root, repo_root, registry, rev_range)
    if to_check:
        scope.vocabulary = build_vocabulary(docs_root, registry, report, to_check, sweep)
    for path in to_check:
        if classify(path, docs_root, settings) == FORBIDDEN:
            report.error(
                path, f"{path.name} does not belong under {docs_root.name}/ -- {settings.forbidden_reason(path)}"
            )
        else:
            check_doc(path, scope, report)

    in_scope = None if sweep else set(targets)
    check_required_notes(docs_root, repo_root, registry, report, in_scope)
    check_numbering(docs_root, registry, report, in_scope)
    if sweep:
        audit_assets(docs_root, settings, report)
    return report, len(to_check)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="doc-marshal check",
        description="Validate notes against the registry. Exits 1 on any error; warnings never fail.",
    )
    parser.add_argument("paths", nargs="*", type=Path, help="notes to check")
    parser.add_argument("--all", action="store_true", help="sweep every note under the docs root (what CI runs)")
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
    add_docs_root_option(parser)
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
    errors, warnings = report.count("error"), report.count("warning")
    if checked or not args.skip_non_notes:
        print(f"\n{checked} {plural(checked)} checked -- {errors} error(s), {warnings} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
