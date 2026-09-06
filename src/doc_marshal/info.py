"""`doc-marshal info`: the effective registry, rendered for a human or an agent.

The convention's prose -- the rules, the argument for each type, the routing guidance -- ships
inside the package and is obtained here. It is never copied into a user's repository: no emitted
copy means no staleness check, no ownership boundary, and no question about whether a rules
file inside the docs root is itself a note. Output is filtered to enabled types, so it is more
accurate than any stored file, and it always matches the installed version.

    doc-marshal info                  # compact: enabled types, one line each, with anchors
    doc-marshal info decision         # one type in full: argument, skeleton, facets, statuses
    doc-marshal info --rules          # the rules that are not per-type
    doc-marshal info --process        # the marshal-the-docs process, staged
    doc-marshal info --format json    # the registry as data, for third parties
    doc-marshal info --dump-toml      # the registry as the configuration schema of a later release
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import __version__
from .config import add_docs_root_option, resolve
from .ontology import STANDARD, DocType, Registry, to_dict, to_toml
from .paths import DocMarshalError
from .settings import NUMBER_TITLE_SEPARATOR

PROSE = Path(__file__).resolve().parent / "prose"


def prose(name: str) -> str:
    return (PROSE / name).read_text(encoding="utf-8")


# --- tables ---------------------------------------------------------------------------------------


def render_types_table(registry: Registry) -> str:
    """The ontology table: one row per enabled type, in the registry's canonical order."""
    rows = [
        "| Type | Serves | Voice | Mutability | Anchor minimum |",
        "| --- | --- | --- | --- | --- |",
    ]
    rows += [
        f"| `{spec.name}` | {spec.serves} | {spec.voice} | {spec.mutability} | {describe_requires(spec, code=True)} |"
        for spec in registry.enabled.values()
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


def render_anchor_table(registry: Registry) -> str:
    """The anchor table, field-major: what each field holds, how it resolves, who must carry it."""
    rows = ["| Field | Contents | Resolves as | Required for |", "| --- | --- | --- | --- |"]
    for name, anchor in registry.anchor_fields.items():
        required = ", ".join(f"`{t}`" for t in registry.required_by(name)) or "no type"
        rows.append(f"| `{name}` | {anchor.contents} | {', '.join(f'`{k}`' for k in anchor.resolves)} | {required} |")
    return "\n".join(rows)


# --- compact --------------------------------------------------------------------------------------


def _placement(spec: DocType) -> str:
    """The mechanical facts of a type that fit on one line."""
    parts: list[str] = []
    if spec.requires:
        parts.append("requires " + describe_requires(spec))
    if spec.fixed_name:
        parts.append(spec.fixed_name + (", one at the docs root" if spec.root_required else ""))
    if spec.folder:
        parts.append(f"{spec.folder}/" + ("NNNN-slug.md" if spec.numbered else ""))
    elif spec.numbered:
        parts.append("NNNN-slug.md")
    if spec.statuses:
        parts.append("status " + "|".join(spec.statuses))
    if spec.append_only:
        parts.append("append-only")
    return "; ".join(parts) or "no anchor"


def render_compact(registry: Registry) -> str:
    types = registry.enabled
    settings = registry.settings
    width = max((len(n) for n in types), default=4)
    serves_width = max((len(s.serves) for s in types.values()), default=6)
    lines: list[str] = [
        (
            f"doc-marshal {__version__} -- preset '{registry.preset}': {len(types)} types, "
            f"{len(registry.anchor_fields)} anchor fields"
        ),
        "",
    ]
    for spec in types.values():
        lines.append(f"  {spec.name.ljust(width)}  {spec.serves.ljust(serves_width)}  {_placement(spec)}")
    anchors = "; ".join(
        f"{name} = {', '.join(a.resolves)}" + (" (drift spine)" if a.on_spine else "")
        for name, a in registry.anchor_fields.items()
    )
    lines.append("")
    lines.append(f"Anchors: {anchors or 'none declared'}.")
    lines.append(
        f"Every note: frontmatter with type, updated (YYYY-MM-DD) and summary (one line, max "
        f"{settings.summary_max} chars); {settings.index_name} is generated."
    )
    return "\n".join(lines)


def render_session_types(registry: Registry) -> str:
    """One line per enabled type -- what it serves and what it must carry -- for session start.

    Terser than `render_compact`: this is paid by every session, so it carries the routing facts
    and nothing else. `doc-marshal info` is one tool call away for the rest.
    """
    types = registry.enabled
    width = max((len(n) for n in types), default=4)
    lines = [
        (
            "Note types (`doc-marshal info <type>` for the argument; `doc-marshal info --process` before "
            "editing docs). Scaffold a new note with `doc-marshal new <type> <path>`: it writes the "
            "sections the type requires."
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


def type_facts(registry: Registry, spec: DocType) -> list[tuple[str, str]]:
    """What the registry says about a type, as (label, fact) pairs: everything `check` enforces
    on a note of it. Rendered aligned by `info <type>` and as a list by the types document, so
    the prose never restates a fact the registry owns."""
    facts: list[tuple[str, str]] = [
        ("serves", spec.serves),
        ("voice", spec.voice),
        ("mutability", spec.mutability),
        ("requires", describe_requires(spec)),
    ]
    facts.append(("frontmatter", ", ".join(f"`{k}`" for k in registry.frontmatter_keys(spec)) + " -- no other key"))
    if spec.statuses:
        default = f"; `new` writes {spec.default_status} when --status is omitted" if spec.default_status else ""
        born = (
            f"; born {' | '.join(spec.birth_statuses)}, never {spec.supersession.status}" if spec.supersession else ""
        )
        facts.append(("status", " | ".join(spec.statuses) + " -- required in the note" + default + born))
    if spec.folder:
        facts.append(("folder", f"{spec.folder}/ at the docs root"))
    if spec.numbered:
        facts.append(("filename", "NNNN-kebab-slug.md, numbers unique within the folder"))
    if spec.fixed_name:
        facts.append(("filename", spec.fixed_name + (", required at the docs root" if spec.root_required else "")))
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


def render_type(registry: Registry, name: str) -> str:
    spec = registry.get(name)
    if spec is None:
        known = ", ".join(registry.enabled)
        raise DocMarshalError(f"no enabled type named {name!r}; the registry has: {known}")
    lines = [f"# `{spec.name}`", ""]
    facts = type_facts(registry, spec)
    width = max(len(k) for k, _ in facts)
    lines += [f"{k.ljust(width)}  {v}" for k, v in facts]
    lines.append("")
    if spec.skeleton:
        lines += ["Skeleton (`doc-marshal new` writes this after the frontmatter and H1):", ""]
        lines += [f"    {line}" for line in spec.skeleton]
        lines.append("")
    argument = type_sections(prose("doc-types.md")).get(spec.name) or spec.description
    if argument:
        lines += [argument.rstrip(), ""]
    return "\n".join(lines).rstrip() + "\n"


# --- long-form prose ------------------------------------------------------------------------------


def render_rules(registry: Registry) -> str:
    settings = registry.settings
    text = prose("rules.md")
    substitutions = {
        "{{types_table}}": render_types_table(registry),
        "{{anchor_table}}": render_anchor_table(registry),
        "{{summary_max}}": str(settings.summary_max),
        "{{index_name}}": settings.index_name,
        "{{assets_dirname}}": settings.assets_dirname,
        "{{marker_name}}": settings.marker_name,
        "{{memory_names}}": ", ".join(f"`{n}`" for n in sorted(settings.memory_names)),
        "{{excluded_dirs}}": ", ".join(f"`{d}/`" for d in sorted(settings.excluded_dirs)),
        "{{spine}}": ", ".join(f"`{n}`" for n in registry.spine) or "no field",
        "{{fixed_names}}": ", ".join(f"`{n}` (`{t}`)" for n, t in registry.fixed_names.items()) or "none",
    }
    for key, value in substitutions.items():
        text = text.replace(key, value)
    return text


def render_doc_types(registry: Registry) -> str:
    """The preamble of doc-types.md, the generated table, then each enabled type: the registry's
    facts as a list, followed by the type's argument from the prose."""
    text = prose("doc-types.md")
    head, _, tail = text.partition("{{types_table}}")
    after, _, _ = tail.partition("\n## `")
    sections = type_sections(text)
    out = [head.rstrip(), "", render_types_table(registry), "", after.strip(), ""]
    for spec in registry.enabled.values():
        out += [f"## `{spec.name}`", ""]
        # The table above already gives serves, voice and mutability.
        out += [
            f"- **{label}:** {fact}"
            for label, fact in type_facts(registry, spec)
            if label not in ("serves", "voice", "mutability")
        ]
        out.append("")
        body = sections.get(spec.name) or spec.description
        if body:
            out += [body.rstrip(), ""]
    return "\n".join(out).rstrip() + "\n"


def render_process() -> str:
    return prose("process.md")


def render_json(registry: Registry) -> str:
    data = to_dict(registry)
    data["version"] = __version__
    data["settings"] = {
        "marker_name": registry.settings.marker_name,
        "index_name": registry.settings.index_name,
        "assets_dirname": registry.settings.assets_dirname,
        "filename_pattern": registry.settings.filename_pattern,
        "summary_max": registry.settings.summary_max,
        "excluded_dirs": sorted(registry.settings.excluded_dirs),
        "memory_names": sorted(registry.settings.memory_names),
        "forbidden_names": registry.settings.forbidden_names,
    }
    return json.dumps(data, indent=2) + "\n"


def resolve_registry(explicit: str | None) -> Registry:
    """The registry in force, or the built-in preset when no docs root is marked.

    `info` is the one command that has something useful to say outside a marked repository -- a
    user reading the convention before adopting it -- so it falls back to the shipped preset.
    """
    try:
        return resolve(explicit)[1]
    except DocMarshalError:
        if explicit:
            raise
        return STANDARD


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="doc-marshal info", description="Render the effective registry and the convention's prose."
    )
    parser.add_argument("type", nargs="?", help="one type in full")
    parser.add_argument("--rules", action="store_true", help="every rule check enforces that is not per-type")
    parser.add_argument("--types", action="store_true", help="every enabled type in full, with the argument for each")
    parser.add_argument("--process", action="store_true", help="the marshal-the-docs process, staged")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument(
        "--dump-toml", action="store_true", help="the registry as the configuration schema of a later release"
    )
    add_docs_root_option(parser)
    args = parser.parse_args(argv)

    registry = resolve_registry(args.docs_root)
    if args.dump_toml:
        sys.stdout.write(to_toml(registry))
    elif args.format == "json":
        sys.stdout.write(render_json(registry))
    elif args.process:
        sys.stdout.write(render_process())
    elif args.rules:
        sys.stdout.write(render_rules(registry))
    elif args.types:
        sys.stdout.write(render_doc_types(registry))
    elif args.type:
        sys.stdout.write(render_type(registry, args.type))
    else:
        print(render_compact(registry))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
