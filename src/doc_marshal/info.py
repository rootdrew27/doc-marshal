"""`doc-marshal info`: the effective profile, rendered for a human or an agent.

The convention's doctrine -- the policies, the argument for each type, the routing guidance --
ships inside the package and is obtained here. It is never copied into a user's repository: no
emitted copy means no staleness check, no ownership boundary, and no question about whether a
policies file inside the docs tree is itself a note. Output is filtered to enabled types, so it is
more accurate than any stored file, and it always matches the installed version.

    doc-marshal info                  # compact: enabled types, one line each, with anchors
    doc-marshal info decision         # one type in full: argument, template, properties, statuses
    doc-marshal info --policies       # the policies that are not per-type
    doc-marshal info --marshalling    # marshalling, staged
    doc-marshal info --format json    # the profile as data, for third parties
    doc-marshal info --dump-toml      # the profile as the configuration schema of a later release
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import __version__
from .config import add_docs_tree_option, resolve
from .errors import DocMarshalError
from .ontology import STANDARD, DocType, Profile, to_dict, to_toml
from .settings import NUMBER_TITLE_SEPARATOR

DOCTRINE = Path(__file__).resolve().parent / "doctrine"


def doctrine(name: str) -> str:
    return (DOCTRINE / name).read_text(encoding="utf-8")


# --- tables ---------------------------------------------------------------------------------------


def render_types_table(profile: Profile) -> str:
    """The ontology table: one row per enabled type, in the profile's canonical order."""
    rows = [
        "| Type | Serves | Voice | Mutability | Anchor minimum |",
        "| --- | --- | --- | --- | --- |",
    ]
    rows += [
        f"| `{spec.name}` | {spec.serves} | {spec.voice} | {spec.mutability} | {describe_requires(spec, code=True)} |"
        for spec in profile.enabled.values()
    ]
    return "\n".join(rows)


def describe_requires(spec: DocType, code: bool = False) -> str:
    """A type's anchor minimum in words: which fields, of which at least one, from which status."""
    if not spec.requires:
        if code:
            return "none"
        return "append-only" if spec.append_only else "no anchor"
    names = [f"`{a}`" if code else a for a in spec.requires]
    text = names[0] if len(names) == 1 else "any of " + ", ".join(names)
    if spec.requires_from:
        text += f" once `{spec.requires_from}`" if code else f" once {spec.requires_from}"
    return text


def render_anchor_table(profile: Profile) -> str:
    """The anchor table, field-major: what each field holds, how it resolves, who must carry it."""
    rows = ["| Field | Contents | Resolves as | Required for |", "| --- | --- | --- | --- |"]
    for name, anchor in profile.anchor_fields.items():
        required = ", ".join(profile.required_by(name)) or "no type"
        rows.append(f"| `{name}` | {anchor.contents} | {', '.join(f'`{k}`' for k in anchor.resolves)} | {required} |")
    return "\n".join(rows)


# --- compact --------------------------------------------------------------------------------------


def _placement(spec: DocType) -> str:
    """The mechanical facts of a type that fit on one line."""
    parts: list[str] = []
    if spec.requires:
        parts.append("requires " + describe_requires(spec))
    if spec.reserved_filename:
        parts.append(spec.reserved_filename + (", one at the top of the docs tree" if spec.root_required else ""))
    if spec.folder:
        parts.append(f"{spec.folder}/" + ("NNNN-slug.md" if spec.numbered else ""))
    elif spec.numbered:
        parts.append("NNNN-slug.md")
    if spec.statuses:
        parts.append("status " + "|".join(spec.statuses))
    if spec.append_only:
        parts.append("append-only")
    return "; ".join(parts) or "no anchor"


def render_compact(profile: Profile) -> str:
    types = profile.enabled
    settings = profile.settings
    width = max((len(n) for n in types), default=4)
    serves_width = max((len(s.serves) for s in types.values()), default=6)
    lines: list[str] = [
        (
            f"doc-marshal {__version__} -- profile '{profile.name}': {len(types)} types, "
            f"{len(profile.anchor_fields)} anchor fields"
        ),
        "",
    ]
    for spec in types.values():
        lines.append(f"  {spec.name.ljust(width)}  {spec.serves.ljust(serves_width)}  {_placement(spec)}")
    anchors = "; ".join(f"{name} = {', '.join(a.resolves)}" for name, a in profile.anchor_fields.items())
    lines.append("")
    lines.append(f"Anchors: {anchors or 'none declared'}.")
    lines.append(
        f"Every note: frontmatter with type, updated (YYYY-MM-DD) and summary (one line, max "
        f"{settings.summary_max} chars); {settings.index_name} is generated."
    )
    return "\n".join(lines)


def render_briefing_types(profile: Profile) -> str:
    """One line per enabled type -- what it serves and what it must carry -- for the briefing.

    Terser than `render_compact`: this is paid by every session, so it carries the routing facts
    and nothing else. `doc-marshal info` is one tool call away for the rest.
    """
    types = profile.enabled
    width = max((len(n) for n in types), default=4)
    lines = [
        (
            "Note types (`doc-marshal info <type>` for the argument; `doc-marshal info --marshalling` "
            "before editing docs). Scaffold a new note with `doc-marshal new <type> <path>`: it writes "
            "the sections the type requires."
        )
    ]
    for spec in types.values():
        lines.append(f"  {spec.name.ljust(width)} {spec.serves} -- {describe_requires(spec)}")
    return "\n".join(lines)


# --- one type -------------------------------------------------------------------------------------

_SECTION_RE = re.compile(r"^## `([a-z0-9_-]+)`\s*$", re.MULTILINE)


def type_sections(text: str) -> dict[str, str]:
    """The per-type sections of doc-types.md, keyed by type name, headings dropped."""
    sections: dict[str, str] = {}
    matches = list(_SECTION_RE.finditer(text))
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[match.end() : end].strip()
        # A trailing `---` rule separates sections in the source file; it is not content.
        body = re.sub(r"\n---\s*$", "", body).strip()
        sections[match.group(1)] = body
    return sections


def type_facts(profile: Profile, spec: DocType) -> list[tuple[str, str]]:
    """What the profile says about a type, as (label, fact) pairs: everything `check` enforces
    on a note of it. Rendered aligned by `info <type>` and as a list by the types document, so
    the doctrine never restates a fact the profile owns."""
    facts: list[tuple[str, str]] = [
        ("serves", spec.serves),
        ("voice", spec.voice),
        ("mutability", spec.mutability),
        ("requires", describe_requires(spec)),
    ]
    facts.append(("frontmatter", ", ".join(f"`{k}`" for k in profile.frontmatter_keys(spec)) + " -- no other key"))
    if spec.statuses:
        default = f"; `new` writes {spec.default_status} when --status is omitted" if spec.default_status else ""
        born = (
            f"; born {' | '.join(spec.birth_statuses)}, never {spec.supersession.status}" if spec.supersession else ""
        )
        facts.append(("status", " | ".join(spec.statuses) + " -- required in the note" + default + born))
    if spec.folder:
        facts.append(("folder", f"{spec.folder}/ at the docs tree"))
    if spec.numbered:
        facts.append(("filename", "NNNN-kebab-slug.md, numbers unique within the folder"))
    if spec.reserved_filename:
        facts.append(
            (
                "reserved filename",
                spec.reserved_filename + (", required at the docs tree" if spec.root_required else ""),
            )
        )
    if spec.additive:
        facts.append(("nesting", "a nested instance adds keys, never redefines an ancestor's"))
    if spec.append_only:
        facts.append(("editing", "append-only -- never edited after acceptance"))
    if spec.supersession:
        s = spec.supersession
        facts.append(
            ("supersession", f"`{s.forward}` / `{s.back}` name the other note; status `{s.status}` requires `{s.back}`")
        )
    if spec.required_sections:
        facts.append(
            (
                "sections",
                ", ".join(f"## {s}" for s in spec.required_sections)
                + " -- required, in this order, each with content; other sections allowed",
            )
        )
    for section, status in spec.empty_at:
        facts.append(("must be empty", f"## {section} once status is {status} (the section itself is optional)"))
    facts.append(("title", "one H1, first" + (f", starting `NNNN{NUMBER_TITLE_SEPARATOR}`" if spec.numbered else "")))
    if spec.structure:
        st = spec.structure
        facts.append(("sections", ", ".join(f"## {s}" for s in st.sections) + " -- exactly, in order"))
        facts.append(
            (
                "table",
                f"under ## {st.table_in}, columns {' | '.join(st.columns)}; key `{st.key_column}`, scanned {', '.join(f'`{c}`' for c in st.scanned_columns)}",
            )
        )
        facts.append(
            (
                "caps",
                f"{st.max_rows} rows, {st.max_cell} chars per {st.body_column.lower()}, {st.max_chars} chars of body outside the table",
            )
        )
    return facts


def render_type(profile: Profile, name: str) -> str:
    spec = profile.get(name)
    if spec is None:
        known = ", ".join(profile.enabled)
        raise DocMarshalError(f"no enabled type named {name!r}; the profile has: {known}")
    lines = [f"# `{spec.name}`", ""]
    facts = type_facts(profile, spec)
    width = max(len(k) for k, _ in facts)
    lines += [f"{k.ljust(width)}  {v}" for k, v in facts]
    lines.append("")
    if spec.template:
        lines += ["Template (`doc-marshal new` writes this after the frontmatter and H1):", ""]
        lines += [f"    {line}" for line in spec.template]
        lines.append("")
    argument = type_sections(doctrine("doc-types.md")).get(spec.name) or spec.description
    if argument:
        lines += [argument.rstrip(), ""]
    return "\n".join(lines).rstrip() + "\n"


# --- long-form doctrine ---------------------------------------------------------------------------


def render_policies(profile: Profile) -> str:
    settings = profile.settings
    text = doctrine("policies.md")
    substitutions = {
        "{{types_table}}": render_types_table(profile),
        "{{anchor_table}}": render_anchor_table(profile),
        "{{summary_max}}": str(settings.summary_max),
        "{{index_name}}": settings.index_name,
        "{{assets_dirname}}": settings.assets_dirname,
        "{{config_name}}": settings.config_name,
        "{{memory_names}}": ", ".join(f"`{n}`" for n in sorted(settings.memory_names)),
        "{{excluded_dirs}}": ", ".join(f"`{d}/`" for d in sorted(settings.excluded_dirs)),
        "{{repo_path_fields}}": ", ".join(f"`{n}`" for n in profile.repo_path_fields) or "no field",
        "{{reserved_filenames}}": ", ".join(f"`{n}` (`{t}`)" for n, t in profile.reserved_filenames.items()) or "none",
    }
    for key, value in substitutions.items():
        text = text.replace(key, value)
    return text


def render_doc_types(profile: Profile) -> str:
    """The preamble of doc-types.md, the generated table, then each enabled type: the profile's
    facts as a list, followed by the type's argument from the doctrine."""
    text = doctrine("doc-types.md")
    head, _, tail = text.partition("{{types_table}}")
    after, _, _ = tail.partition("\n## `")
    sections = type_sections(text)
    out = [head.rstrip(), "", render_types_table(profile), "", after.strip(), ""]
    for spec in profile.enabled.values():
        out += [f"## `{spec.name}`", ""]
        # The table above already gives serves, voice and mutability.
        out += [
            f"- **{label}:** {fact}"
            for label, fact in type_facts(profile, spec)
            if label not in ("serves", "voice", "mutability")
        ]
        out.append("")
        body = sections.get(spec.name) or spec.description
        if body:
            out += [body.rstrip(), ""]
    return "\n".join(out).rstrip() + "\n"


def render_marshalling() -> str:
    return doctrine("marshalling.md")


def render_json(profile: Profile) -> str:
    data = to_dict(profile)
    data["version"] = __version__
    data["settings"] = {
        "config_name": profile.settings.config_name,
        "index_name": profile.settings.index_name,
        "assets_dirname": profile.settings.assets_dirname,
        "filename_pattern": profile.settings.filename_pattern,
        "summary_max": profile.settings.summary_max,
        "excluded_dirs": sorted(profile.settings.excluded_dirs),
        "memory_names": sorted(profile.settings.memory_names),
        "forbidden_names": profile.settings.forbidden_names,
    }
    return json.dumps(data, indent=2) + "\n"


def resolve_profile(explicit: str | None) -> Profile:
    """The profile in force, or the built-in one when no docs tree is marked.

    `info` is the one command that has something useful to say outside a marked repository -- a
    user reading the convention before adopting it -- so it falls back to the shipped profile.
    """
    try:
        return resolve(explicit)[1]
    except DocMarshalError:
        if explicit:
            raise
        return STANDARD


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="doc-marshal info", description="Render the effective profile and the convention's doctrine."
    )
    parser.add_argument("type", nargs="?", help="one type in full")
    parser.add_argument("--policies", action="store_true", help="every policy check enforces that is not per-type")
    parser.add_argument("--types", action="store_true", help="every enabled type in full, with the argument for each")
    parser.add_argument("--marshalling", action="store_true", help="marshalling, staged")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument(
        "--dump-toml", action="store_true", help="the profile as the configuration schema of a later release"
    )
    add_docs_tree_option(parser)
    args = parser.parse_args(argv)

    profile = resolve_profile(args.docs_tree)
    if args.dump_toml:
        sys.stdout.write(to_toml(profile))
    elif args.format == "json":
        sys.stdout.write(render_json(profile))
    elif args.marshalling:
        sys.stdout.write(render_marshalling())
    elif args.policies:
        sys.stdout.write(render_policies(profile))
    elif args.types:
        sys.stdout.write(render_doc_types(profile))
    elif args.type:
        sys.stdout.write(render_type(profile, args.type))
    else:
        print(render_compact(profile))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
