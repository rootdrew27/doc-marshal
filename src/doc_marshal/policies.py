"""The policies `check` enforces -- naming, frontmatter, anchors, links, location, structure,
vocabulary -- as one pipeline.

Every per-note policy takes the same three things: the `Note` read once for it, the `Scope` of the
run, and the `Report` to write findings to. `NOTE_POLICIES` lists them in the order their findings
are emitted; `run` in `check` iterates it and nothing else. A policy that only means something for
a note whose type resolved returns early when `note.spec` is None. Tree-wide policies take the scope
and the report, and `TREE_POLICIES` lists those. `PLACEMENT_POLICIES` is the subset `new` runs on a
path before writing it, so the two commands cannot disagree about where a note goes.

Every policy that varies by type is read off the effective profile rather than branched on by name,
so a new type is a profile entry and nothing here changes.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import cached_property
from pathlib import Path
from urllib.parse import unquote, urlparse

from .anchors import check_anchor
from .drifted import matches
from .frontmatter import anchor_entries
from .git import Git
from .markdown import cell_items, cell_text, heading_lines, headings, parse_table, sections, table_chars
from .note import Note
from .ontology import Profile
from .paths import exists_exact, rel_to
from .report import Report
from .settings import NOTE_SUFFIX, NUMBER_PREFIX_RE, NUMBER_TITLE_SEPARATOR
from .vocabulary import Vocabulary, alias_re

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# A link or an image: the destination is either `<...>` (CommonMark's spelling for a destination
# holding spaces) or a run without spaces or a closing paren.
LINK_RE = re.compile(r"\[[^\]]*\]\((?:<([^>]+)>|([^)\s]+))\)")
WIKILINK_RE = re.compile(r"\[\[[^\]]+\]\]")


@dataclass
class Scope:
    """What one run knows once, handed to every policy.

    The git facts are read on first use and never twice: which notes the change touched, for the
    freshness check on every note; what it touched outside the docs and the day it began, which
    only a note that gets past the cheaper tests ever asks for. None from any of them means git
    could not say -- "cannot tell" is not "nothing edited", and the checks stay quiet.

    `in_scope` is the set of targets a tree-wide policy may report on, or None for a sweep: a run
    that touched one reference note should not fail on a file it never opened.

    `git` is the port every git question goes through, built by the command for the repository
    the run is in; `repo_root` is read off it, so the two cannot disagree.
    """

    docs_tree: Path
    profile: Profile
    git: Git
    rev_range: str | None = None
    vocabulary: Vocabulary = field(default_factory=Vocabulary)
    headings_of: dict[Path, set[str]] = field(default_factory=dict)  # linked notes, read once
    in_scope: set[Path] | None = None

    @property
    def repo_root(self) -> Path:
        return self.git.repo_root

    @cached_property
    def edited(self) -> set[Path] | None:
        return self.git.edited_notes(self.rev_range, self.docs_tree)

    @cached_property
    def changed(self) -> set[str]:
        return self.git.changed_paths(self.rev_range)

    @cached_property
    def since(self) -> date | None:
        return self.git.change_start(self.rev_range)

    def touched(self, path: Path) -> bool:
        """Whether the change edited this note, as far as git can tell."""
        return self.edited is not None and path in self.edited


Policy = Callable[[Note, Scope, Report], None]
TreePolicy = Callable[[Scope, Report], None]


# --- per-note ------------------------------------------------------------------------------------


def check_naming(note: Note, scope: Scope, report: Report) -> None:
    """Notes and the folders holding them match the filename pattern.

    A type may reserve one exact filename instead and those are exempt. The exemption is read off
    the effective profile rather than granted to upper-case names generally, so a stray `NOTES.md` is still the
    naming error it was before.
    """
    path, profile = note.path, scope.profile
    settings = profile.settings
    if path.name not in profile.reserved_filenames and not settings.name_re.match(path.stem):
        report.error(path, f"filename is not kebab-case: {path.name}")
    for part in rel_to(path, scope.docs_tree).parts[:-1]:
        if not settings.name_re.match(part):
            report.error(path, f"folder is not kebab-case: {part}/")


def check_frontmatter(note: Note, scope: Scope, report: Report) -> None:
    """The frontmatter parsed, names a live type, and every field it carries is one the type
    allows and holds what its policy requires."""
    path, meta, spec, profile = note.path, note.meta, note.spec, scope.profile
    if meta is None:
        assert note.error is not None  # read_note returns one or the other
        report.error(path, note.error)
        return
    settings = profile.settings
    if spec is None:
        report.error(path, f"'type' must be one of {sorted(profile.enabled)}, got {meta.get('type')!r}")

    updated = meta.get("updated")
    if not isinstance(updated, str) or not DATE_RE.match(updated):
        report.error(path, f"'updated' must be an ISO date (YYYY-MM-DD), got {updated!r}")

    summary = meta.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        report.error(path, "'summary' is required -- it is the only text the generated index shows")
    elif len(summary) > settings.summary_max:
        report.error(path, f"'summary' must be one short line (max {settings.summary_max} chars)")

    status = meta.get("status")
    # Which anchors a type must carry is profile data: at least one of `requires`, and only from
    # the status `requires_from` names when it names one. Each field's own validation follows from
    # its `resolves` kinds and runs whenever the field is present, required or not.
    if spec is not None and spec.anchors_required(status) and not any(meta.get(n) for n in spec.requires):
        names = " or ".join(f"'{n}'" for n in spec.requires)
        since = f" once status is '{spec.requires_from}'" if spec.requires_from else ""
        what = "; ".join(f"{n}: {profile.anchor_fields[n].contents}" for n in spec.requires)
        report.error(path, f"type '{spec.name}' requires {names}{since} -- {what}")
    for name, anchor in profile.anchor_fields.items():
        if meta.get(name) is not None:
            check_anchor(path, anchor, meta[name], scope.docs_tree, scope.git, profile, report)

    if spec is None:
        return

    if spec.statuses and status not in spec.statuses:
        report.error(path, f"{spec.name} 'status' must be one of {sorted(spec.statuses)}, got {status!r}")

    if spec.supersession is not None:
        supersession = spec.supersession
        for key in (supersession.forward, supersession.back):
            other = meta.get(key)
            if not isinstance(other, str):
                continue
            target = (path.parent / other).resolve()
            if target == path:
                report.error(path, f"'{key}' names this note itself: {other}")
            elif not exists_exact(scope.repo_root, target):
                report.error(path, f"'{key}' names a {spec.name} that does not exist: {other}")
        if status == supersession.status and supersession.back not in meta:
            report.error(path, f"status is '{supersession.status}' but no '{supersession.back}' is named")
        if supersession.back in meta and status != supersession.status:
            report.error(
                path,
                f"'{supersession.back}' is named but status is {status!r} -- a replaced {spec.name} says "
                f"'status: {supersession.status}'",
            )

    # A key the type does not declare is a typo or a private convention, and both used to pass
    # unread: `code-refs` anchored nothing and validated as if it had. The set is the profile's,
    # so a declared anchor field is legal on every type and a status only where the type has one.
    known = profile.frontmatter_keys(spec)
    for key in meta:
        if key not in known:
            report.error(
                path,
                f"unknown frontmatter key '{key}' -- a '{spec.name}' note may carry {', '.join(known)}",
            )


def check_location(note: Note, scope: Scope, report: Report) -> None:
    """A type that names a folder, a numbering scheme or a filename is placed and named by it."""
    path, spec, profile = note.path, note.spec, scope.profile
    if spec is None:
        return
    if spec.folder is not None and path.parent != spec.home(scope.docs_tree):
        where = rel_to(path.parent, scope.docs_tree)
        report.error(path, f"a '{spec.name}' note belongs in {spec.folder}/, not {where}/")
    if spec.numbered and not profile.settings.numbered_name_re.match(path.stem):
        report.error(path, f"a '{spec.name}' filename must be NNNN-kebab-slug.md")

    # A reserved filename binds in both directions. One way alone leaves a hole: a `nomenclature` note
    # under another name is unfindable by the checks that glob for it, and any other type wearing
    # the name would be picked up by them and parsed as something it is not.
    if spec.reserved_filename is not None and path.name != spec.reserved_filename:
        report.error(path, f"a '{spec.name}' note must be named {spec.reserved_filename}")
    owner = profile.reserved_filenames.get(path.name)
    if owner is not None and owner != spec.name:
        report.error(path, f"{path.name} is the '{owner}' type's filename, but this declares '{spec.name}'")


def check_lead(note: Note, scope: Scope, report: Report) -> None:
    """A note anchored from a status onward was edited while none of the code it anchors to was.

    Such a note describes what is built, so an edit to it with no edit to the code means either a
    correction or the doc moving ahead of the code. Only the author knows which, and the second
    means the status is no longer true: the profile says which status precedes the anchored one,
    and the warning names it. Silent when git cannot say what changed.
    """
    path, meta, spec = note.path, note.meta, note.spec
    if spec is None or meta is None:
        return
    if spec.requires_from is None or meta.get("status") != spec.requires_from or not scope.touched(path):
        return
    refs = [ref for name in scope.profile.repo_path_fields for ref in anchor_entries(meta, name)]
    if not refs or any(matches(ref, scope.changed) for ref in refs):
        return
    index = spec.statuses.index(spec.requires_from)
    before = f"'{spec.statuses[index - 1]}'" if index > 0 else "an earlier status"
    report.warn(
        path,
        f"edited while none of its code was ({', '.join(refs)}) -- if the doc now leads the code, "
        f"set status to {before} until the code catches up",
    )


def check_freshness(note: Note, scope: Scope, report: Report) -> None:
    """`updated` names a real past date, and an edited note has had it bumped.

    The format check lives in `check_frontmatter`; this runs only once the field parses, and so
    says nothing about a note whose frontmatter did not. A date in the future is an error --
    nothing can have been edited then -- with a day of slack so a writer ahead of CI's UTC clock
    is not failed for it.

    An edited note's date must be no earlier than the day the change began: today for a
    working-tree run, the earliest commit's day for a range. That makes the policy purely mechanical
    -- a note dated the day it was edited stays valid however long its pull request takes -- and
    so it is an error. Silent when git could not say what was edited or when.
    """
    path = note.path
    updated = note.meta.get("updated") if note.meta is not None else None
    if not isinstance(updated, str) or not DATE_RE.match(updated):
        return
    try:
        stamp = date.fromisoformat(updated)
    except ValueError:
        report.error(path, f"'updated' is not a real date: {updated}")
        return
    today = date.today()
    if stamp > today + timedelta(days=scope.profile.settings.future_slack_days):
        report.error(path, f"'updated' is in the future: {updated}")
        return
    if not scope.touched(path) or scope.since is None or stamp >= scope.since:
        return
    window = f" (the change began on {scope.since})" if scope.since != today else ""
    report.error(path, f"edited by this change but 'updated' still reads {updated} -- bump it to {today}{window}")


def check_title(note: Note, scope: Scope, report: Report) -> None:
    """One H1, first, and for a numbered note carrying the number its filename does.

    A note without a title has nothing for a reader or an index to call it; a second H1 is two
    notes in one file. The number in the title is what `new` writes, and the filename is the
    source of truth for it, so the two drifting apart is caught here rather than read as a
    typo. Read outside fences, where a `# comment` is code.
    """
    path, spec = note.path, note.spec
    levels = list(heading_lines(note.plain))
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


def check_sections(note: Note, scope: Scope, report: Report) -> None:
    """A free-form type's required sections are present, once each, in order, and say something.

    The template wrote every one of these, so a missing section was deleted and an empty one was
    never written; both are what `check` exists to catch before a reader does. Other sections are
    the author's. Comments are read out of the body first, so a section holding only its scaffold
    comment is blank. A section the type wants empty from a status onward is the reverse check:
    a `done` spec with an open question is not done.
    """
    path, meta, spec = note.path, note.meta, note.spec
    if spec is None or meta is None:
        return
    found = sections(note.plain)
    names = [name for name, _ in found]
    required = ", ".join(f"## {s}" for s in spec.required_sections)
    positions: list[int] = []
    for name in spec.required_sections:
        count = names.count(name)
        if count == 0:
            report.error(path, f"missing '## {name}' -- a '{spec.name}' note carries {required}, in that order")
            continue
        if count > 1:
            report.error(path, f"'## {name}' appears {count} times -- a required section appears once")
        index = names.index(name)
        positions.append(index)
        if not "\n".join(found[index][1]).strip():
            report.error(path, f"'## {name}' is empty -- a required section says something, even in one line")
    if positions != sorted(positions):
        order = ", ".join(f"## {s}" for s in names if s in spec.required_sections)
        report.error(path, f"sections out of order: got {order}; a '{spec.name}' note carries {required}")
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


def check_structure(note: Note, scope: Scope, report: Report) -> None:
    """A type whose body is data is validated for shape, not just for text.

    Every one of these is an error rather than a warning. The shape is what other checks parse: a
    renamed column or a dropped section does not degrade them, it silently turns them off, and a
    check that has quietly stopped running is worse than one that never existed.

    `max_chars` is measured on the raw body with the table's rows taken out: the rows are
    `max_rows`' business, the text around them is this cap's, and the frontmatter is neither --
    a briefing never sees it.

    Keys are compared case-insensitively: `Widget` and `widget` are one term twice, and an alias
    that is also a term rules out the word the table defines.
    """
    path, spec = note.path, note.spec
    if spec is None:
        return
    structure = spec.structure
    if structure is None:
        return
    text, body = note.text, note.body

    found = [name for name, _ in sections(text)]
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
            f"'{spec.name}' note is emitted into every briefing; the text around its table is "
            f"capped at {structure.max_chars} (the table at {structure.max_rows} rows)",
        )

    header, rows, malformed = parse_table(text, structure.table_in)
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


def check_vocabulary(note: Note, scope: Scope, report: Report) -> None:
    """A note's text uses the vocabulary's terms rather than the aliases it rules out.

    A warning, not an error: the scan is a word match and cannot see intent, and a false positive
    that blocks a commit would be worse than the drift it catches.

    The frontmatter `summary` is scanned with the body: it is the one line every briefing carries.
    The scan view is the body with its comments, fenced blocks and code spans removed: comments
    are notes to the author, and a banned alias is routinely the literal name of a field or an
    API, with backticks the way you say so. Two exemptions, both structural. An append-only type
    is skipped because its wording cannot lawfully be corrected. A vocabulary note is skipped
    because the aliases are its content.
    """
    path, meta, spec = note.path, note.meta, note.spec
    if spec is None or meta is None or spec.append_only or spec.is_vocabulary_source:
        return
    banned = scope.vocabulary.aliases_for(path)
    if not banned:
        return
    summary = meta.get("summary")
    text = f"{summary}\n\n{note.scan}" if isinstance(summary, str) else note.scan
    for alias in sorted(banned):
        if alias_re(alias).search(text):
            report.warn(
                path,
                f"'{alias}' is an alias the vocabulary rules out -- use "
                f"'{banned[alias]}' instead, or put it in backticks if it is a literal name",
            )


def check_links(note: Note, scope: Scope, report: Report) -> None:
    """Every link and image is a resolving relative path; wikilinks are not a link style here.

    A target is resolved with exact spelling and must stay inside the repository: a link that
    leaves it is broken for every clone but this one. Links are read from the scan view, the text
    with its code spans removed, the way the alias scan reads it: backticks are how a note quotes a
    link rather than makes one. The note's own headings are read from the text, spans intact,
    because a backtick in a heading is part of its slug. A heading anchor must match the slug
    GitHub would make, case included, because that is the resolver a reader's click goes
    through. A linked note's headings are read once per run, however many notes link into it.
    """
    path, scan = note.path, note.scan
    for raw in WIKILINK_RE.findall(scan):
        report.error(path, f"wikilink -- use a relative markdown link instead: {raw}")

    own = headings(note.text)
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


# --- tree-wide -----------------------------------------------------------------------------------


def check_required_notes(scope: Scope, report: Report) -> None:
    """A type the effective profile marks `root_required` has an instance at the top of the docs tree.

    Scoped like `check_numbering`: a run that touched one reference note should not fail on a file
    it never opened. A sweep reports it, and so does a run that names the missing file itself.
    """
    docs_tree, repo_root, in_scope = scope.docs_tree, scope.repo_root, scope.in_scope
    for spec in scope.profile.root_notes:
        target = spec.reserved_path(docs_tree)
        if exists_exact(repo_root, target):
            continue
        if in_scope is not None and not any(p.name == spec.reserved_filename for p in in_scope):
            continue
        report.error(
            target,
            f"missing -- every docs tree carries a '{spec.name}' note at "
            f"{rel_to(docs_tree, repo_root)}/{spec.reserved_filename}",
        )


def check_numbering(scope: Scope, report: Report) -> None:
    """Within each numbered type's folder, numbers are unique.

    `in_scope` limits which collisions are reported: a run that touched one reference doc should
    not fail on two decision files it never opened. None reports every collision.
    """
    profile, in_scope = scope.profile, scope.in_scope
    for spec in profile.enabled.values():
        if not spec.numbered:
            continue
        folder = spec.home(scope.docs_tree)
        if not folder.is_dir():
            continue
        if in_scope is not None and not any(p.parent == folder for p in in_scope):
            continue
        seen: dict[str, Path] = {}
        for path in sorted(folder.glob(f"*{NOTE_SUFFIX}")):
            match = profile.settings.numbered_name_re.match(path.stem)
            if not match:
                continue
            number = match.group(1)
            other = seen.get(number)
            if other is None:
                seen[number] = path
                continue
            if in_scope is None or {path, other} & in_scope:
                report.error(path, f"duplicate {spec.name} number {number} (also {other.name})")


def audit_assets(scope: Scope, report: Report) -> None:
    """Departures from the asset-directory convention.

    Errors, like every policy about shape: a markdown file under `assets/` is never validated or
    indexed, and a nested `assets/` is not exempt, so either is a file the tree has quietly
    stopped governing. Only a sweep reports them -- they are facts about the tree, not a note.
    """
    if scope.in_scope is not None:
        return
    docs_tree, settings = scope.docs_tree, scope.profile.settings
    assets = docs_tree / settings.assets_dirname
    if assets.is_dir():
        for path in sorted(assets.rglob(f"*{NOTE_SUFFIX}")):
            report.error(
                path,
                f"markdown under {settings.assets_dirname}/ -- that directory holds assets "
                "only, so this file is never validated or indexed",
            )
    for path in sorted(docs_tree.rglob(settings.assets_dirname)):
        if path.is_dir() and path.parent != docs_tree:
            report.error(
                path,
                f"nested {settings.assets_dirname}/ -- assets belong in the one "
                f"{settings.assets_dirname}/ at the top of the docs tree, and this one is not exempt",
            )


# --- the pipeline --------------------------------------------------------------------------------

# In emission order. The read error is reported by `check_frontmatter`, and every policy that needs
# a resolved type returns early without one, so one flat list serves every note.
NOTE_POLICIES: tuple[Policy, ...] = (
    check_naming,
    check_frontmatter,
    check_location,
    check_lead,
    check_freshness,
    check_title,
    check_sections,
    check_structure,
    check_vocabulary,
    check_links,
)

TREE_POLICIES: tuple[TreePolicy, ...] = (check_required_notes, check_numbering, audit_assets)

# What `new` holds a path to before writing: the naming and placement policies, and only those.
PLACEMENT_POLICIES: tuple[Policy, ...] = (check_naming, check_location)
