"""The ontology as data: anchor fields, doc types, and the `standard` preset.

`DocType` is the single internal representation. The validator enforces from it, the scaffolder
writes from it, and `info` renders it -- no check hardcodes a type name. The preset is constructed
in Python so its docstrings, type checking and cross-references (`Structure(max_cell=summary_max)`)
survive; `from_dict` is the alternate constructor the 0.2 config loader builds on, and `to_toml` is
the serializer behind `info --dump-toml`. The round-trip test between the two is the forcing
function: if the schema cannot express the shipped preset, the schema is too weak.

What is *not* here: why each type exists and how to route between them. That is `prose/`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from typing import Any

from .settings import SETTINGS, Settings

# How an anchor field's entries resolve. Only `repo-path` is on the drift spine.
RESOLVES = ("repo-path", "docs-path", "url", "opaque")
SPINE = "repo-path"

# The shared lifecycle a living note may carry: written before the thing exists, being built or
# reconciled, or matching what is built. A type opts in by naming it as its `statuses`; a type with
# its own vocabulary (a decision is accepted or superseded, never "done") declares that instead.
LIFECYCLE = ("proposed", "in-progress", "done")


@dataclass(frozen=True)
class AnchorField:
    """One declarable anchor field: what it holds and how its entries resolve.

    An entry is valid when *any* listed kind accepts it, so `source` -- declared as `docs-path` or
    `url` -- takes either. The engine reads `resolves` and nothing else about the field, which is
    what lets a user declare a third field, or make every field `opaque` and float free of the
    spine, in one config table.
    """

    name: str
    contents: str  # prose: what the field holds, rendered by `info` and in error messages
    resolves: tuple[str, ...]

    def __post_init__(self) -> None:
        unknown = [kind for kind in self.resolves if kind not in RESOLVES]
        if unknown or not self.resolves:
            raise ValueError(
                f"anchor field {self.name!r}: resolves must name one or more of {RESOLVES}, "
                f"got {self.resolves!r}"
            )

    @property
    def on_spine(self) -> bool:
        return SPINE in self.resolves


@dataclass(frozen=True)
class Structure:
    """The shape a type's body must take, for a type that scripts read as well as people.

    Most types are prose and are validated only for frontmatter, links and naming. A type whose
    body is *data* -- a table other checks parse -- needs its shape fixed, because a reformatted
    table silently turns every check built on it into a no-op. Stating the shape in the registry
    keeps the rule with the rest of the type, and means a second parsed type needs no new code.

    `max_chars` bounds the whole file, frontmatter included, because the note is emitted with it.
    It exists for a type injected into every session, where size is a cost paid forever.
    """

    sections: tuple[str, ...]  # the exact set of `##` headings, in this order
    table_in: str  # the section holding the table the columns below describe
    columns: tuple[str, ...]  # the table's header row, exactly
    key_column: str  # the column naming the thing each row defines
    body_column: str  # the column `max_cell` bounds
    scanned_columns: tuple[str, ...]  # columns whose entries other notes are checked against
    max_rows: int
    max_cell: int
    max_chars: int


@dataclass(frozen=True)
class Supersession:
    """How a type points at the entry that replaced it.

    The field names and the status that requires the back-pointer are data, so a second type that
    supersedes -- or a rename of either field -- is a registry edit and nothing else.
    """

    forward: str = "supersedes"
    back: str = "superseded_by"
    status: str = "superseded"


@dataclass(frozen=True)
class DocType:
    """One type in the ontology.

    `serves`, `voice` and `mutability` are prose that only `info` renders. Everything after them is
    a mechanical fact: the validator enforces it and the scaffolder applies it.
    """

    name: str
    serves: str
    voice: str
    mutability: str
    enabled: bool = True  # `enabled = false` in config removes the type from the live registry
    requires: tuple[str, ...] = ()  # anchor fields of which a note must carry at least one -- a minimum, not a permitted set
    requires_from: str | None = None  # the `status` from which `requires` is enforced; None means always
    statuses: tuple[str, ...] = ()  # allowed `status` values; empty means the type has no status
    default_status: str | None = None  # what `new` writes when --status is omitted
    folder: str | None = None  # the one folder under the docs root this type lives in
    numbered: bool = False  # the filename carries a unique `NNNN-` prefix
    supersession: Supersession | None = None  # how this type records being replaced
    skeleton: tuple[str, ...] = ()  # what `new` writes; `{today}` is substituted
    fixed_name: str | None = None  # the one filename this type may take, exempt from the naming pattern
    root_required: bool = False  # one instance must exist at the docs root
    additive: bool = False  # a nested instance may not redefine a key an ancestor defines
    append_only: bool = False  # never edited after acceptance, so its wording cannot be corrected
    structure: Structure | None = None  # the body shape other checks parse -- see `Structure`
    description: str = ""  # longer prose for a user-declared type; the preset's lives in prose/

    def requires_anchor(self, name: str) -> bool:
        return name in self.requires

    def anchors_required(self, status: object) -> bool:
        """Whether `requires` binds a note in the given status. A type that anchors only from a
        certain status -- a spec, which names no code until the code exists -- is unanchored
        before it, and always anchored when it has no such threshold."""
        return bool(self.requires) and (self.requires_from is None or status == self.requires_from)


# Facet names an anchor field may not take, because a type's TOML table spells anchor requirements
# as `<field> = true` beside the facets.
_FACETS = frozenset(f.name for f in fields(DocType))


@dataclass(frozen=True)
class Registry:
    """The effective ontology: every declared anchor field and every type, live or not."""

    preset: str
    anchor_fields: dict[str, AnchorField]
    types: dict[str, DocType]
    settings: Settings = field(default=SETTINGS)

    def __post_init__(self) -> None:
        for name in self.anchor_fields:
            if name in _FACETS:
                raise ValueError(f"anchor field {name!r} collides with a type facet of that name")
        for spec in self.types.values():
            for name in spec.requires:
                if name not in self.anchor_fields:
                    raise ValueError(
                        f"type {spec.name!r} requires undeclared anchor field {name!r}"
                    )
            if spec.structure is not None:
                missing = [
                    c
                    for c in (spec.structure.key_column, spec.structure.body_column, *spec.structure.scanned_columns)
                    if c not in spec.structure.columns
                ]
                if missing:
                    raise ValueError(f"type {spec.name!r}: structure names columns it lacks: {missing}")
                if spec.structure.table_in not in spec.structure.sections:
                    raise ValueError(f"type {spec.name!r}: structure.table_in is not one of its sections")
            if spec.default_status is not None and spec.default_status not in spec.statuses:
                raise ValueError(f"type {spec.name!r}: default_status is not one of its statuses")
            if spec.requires_from is not None and spec.requires_from not in spec.statuses:
                raise ValueError(f"type {spec.name!r}: requires_from is not one of its statuses")

    @property
    def enabled(self) -> dict[str, DocType]:
        """The live types, in canonical order. Every consumer reads this, never `types`."""
        return {name: spec for name, spec in self.types.items() if spec.enabled}

    def get(self, name: object) -> DocType | None:
        """The live type of that name, or None."""
        if not isinstance(name, str):
            return None
        spec = self.types.get(name)
        return spec if spec is not None and spec.enabled else None

    @property
    def fixed_names(self) -> dict[str, str]:
        """Filenames a live type claims outright, mapped to the type. Read off the registry, so the
        naming check exempts exactly what some type requires, and nothing else."""
        return {spec.fixed_name: spec.name for spec in self.enabled.values() if spec.fixed_name}

    @property
    def spine(self) -> tuple[str, ...]:
        """The drift spine: anchor fields whose entries resolve as repo paths. `affected` matches
        these, and only these, against a diff."""
        return tuple(name for name, f in self.anchor_fields.items() if f.on_spine)

    def required_by(self, anchor: str) -> tuple[str, ...]:
        return tuple(spec.name for spec in self.enabled.values() if spec.requires_anchor(anchor))


def standard(settings: Settings = SETTINGS) -> Registry:
    """The `standard` preset: five types, two anchor fields.

    A type names the reader it serves, and nothing else: look a fact up, run a procedure, read a
    feature's behaviour as a whole, reopen a settled choice, choose what to call a thing. Whether a
    fact was decided here or observed from outside is a property of the fact, so `reference` accepts
    either anchor and requires at least one. Whether the thing described exists yet is a lifecycle,
    so `spec` carries `status` and is anchored only once it is `done`.

    `requires` lists the anchor fields of which a note must carry at least one. These are minimums,
    not permitted sets: any declared field is legal on any type and is validated whenever present.

    Two types require no anchor. `decision` is append-only and anchored by its own content. A
    `context` note is falsified by the words the repo uses, not by a path, and anchoring it to code
    would flag a vocabulary on every unrelated change.

    Order is canonical: it is the order `info` lists the types in, from the most common to the least.
    """
    anchors = {
        "code_refs": AnchorField(
            "code_refs", "paths to the code this note describes", ("repo-path",)
        ),
        "source": AnchorField(
            "source", "URLs, or paths to an attachment or another note", ("docs-path", "url")
        ),
    }
    types = (
        DocType(
            name="reference",
            serves="someone looking up a fact -- decided by this repo, or observed from outside it",
            voice="flat, enumerative, cites its source",
            mutability="living -- rewritten in place as the code or the world changes",
            requires=("code_refs", "source"),
            skeleton=(
                "<!-- Tables and definition lists. Present tense. No procedures. Cite the source of",
                "     any fact from outside the repo, and distinguish specified from measured. -->",
            ),
        ),
        DocType(
            name="runbook",
            serves="someone running a procedure",
            voice="imperative, literal, copy-pasteable",
            mutability="living -- rewritten in place",
            requires=("code_refs",),
            skeleton=(
                "<!-- Imperative. Literal, copy-pasteable commands. Name the condition before the",
                "     action where the path branches. Cheapest and least destructive step first. -->",
            ),
        ),
        DocType(
            name="decision",
            serves="someone about to reopen a settled choice",
            voice="terse, one decision",
            mutability="append-only -- never edited after acceptance",
            statuses=("accepted", "superseded"),
            default_status="accepted",
            folder="decisions",
            numbered=True,
            append_only=True,
            supersession=Supersession(),
            skeleton=(
                "## Context",
                "",
                "<!-- What forced a choice: the constraint, the failure, the requirement. -->",
                "",
                "## Decision",
                "",
                "<!-- What was decided, in the active voice. -->",
                "",
                "## Alternatives considered",
                "",
                "<!-- Each one, and the specific reason it lost. This is what stops the question being reopened. -->",
                "",
                "## Consequences",
                "",
                "<!-- What this makes easy, what it makes hard, what it commits us to. -->",
            ),
        ),
        DocType(
            name="spec",
            serves="someone reading, building or validating a feature's behaviour as a whole",
            voice="declarative, whole-feature, links to the references that justify it",
            mutability="living at every status -- in-progress whenever the doc leads the code",
            statuses=LIFECYCLE,
            default_status="proposed",
            requires=("code_refs",),
            requires_from="done",
            skeleton=(
                "## Overview",
                "",
                "<!-- The feature in a paragraph: what it is for, and where it starts and stops. -->",
                "",
                "## Behavior",
                "",
                "<!-- What it does, as statements. Link each fact to the reference note that holds it. -->",
                "",
                "## Validation",
                "",
                "<!-- Stable identifiers so one item can be ticked off without renumbering the rest. -->",
                "",
                "- [ ] **V1** --",
            ),
        ),
        DocType(
            name="context",
            serves="someone choosing what to call a thing",
            voice="flat, definitional, opinionated",
            mutability="living -- rewritten as the domain sharpens",
            fixed_name="CONTEXT.md",
            root_required=True,
            additive=True,
            structure=Structure(
                sections=("Terminology", "Relationships", "Ambiguities"),
                table_in="Terminology",
                columns=("Term", "Definition", "Avoid", "Historical"),
                key_column="Term",
                body_column="Definition",
                scanned_columns=("Avoid",),
                max_rows=35,
                max_cell=settings.summary_max,
                max_chars=6000,
            ),
            skeleton=(
                "<!-- One line on what this context covers. Terms specific to it, never general",
                "     programming concepts. Be opinionated: one word per concept. -->",
                "",
                "## Terminology",
                "",
                "| Term | Definition | Avoid | Historical |",
                "| --- | --- | --- | --- |",
                "",
                "## Relationships",
                "",
                "<!-- How the terms above relate. One per line. Omit if none do. -->",
                "",
                "## Ambiguities",
                "",
                "<!-- Live concerns only. A resolved one is deleted or becomes a decision. -->",
            ),
        ),
    )
    return Registry("standard", anchors, {t.name: t for t in types}, settings)


PRESETS = {"standard": standard}

STANDARD = standard()


# --- serialization ------------------------------------------------------------------------------
#
# The TOML shape 0.2's `.doc-marshal.toml` takes. Written now so the round-trip test can run on day
# one, and so `info --dump-toml` shows a user the worked example of the schema they will configure.


def to_dict(registry: Registry) -> dict[str, Any]:
    """The registry as plain data, in the shape the config file takes."""
    out: dict[str, Any] = {"extends": [], "anchors": {}, "types": {}}
    for name, anchor in registry.anchor_fields.items():
        out["anchors"][name] = {"contents": anchor.contents, "resolves": list(anchor.resolves)}
    for name, spec in registry.types.items():
        table: dict[str, Any] = {
            "serves": spec.serves,
            "voice": spec.voice,
            "mutability": spec.mutability,
            "enabled": spec.enabled,
        }
        for anchor in registry.anchor_fields:
            table[anchor] = spec.requires_anchor(anchor)
        if spec.statuses:
            table["statuses"] = list(spec.statuses)
        if spec.default_status is not None:
            table["default_status"] = spec.default_status
        if spec.folder is not None:
            table["folder"] = spec.folder
        table["numbered"] = spec.numbered
        if spec.fixed_name is not None:
            table["fixed_name"] = spec.fixed_name
        table["root_required"] = spec.root_required
        table["additive"] = spec.additive
        table["append_only"] = spec.append_only
        if spec.requires_from is not None:
            table["requires_from"] = spec.requires_from
        if spec.description:
            table["description"] = spec.description
        table["skeleton"] = list(spec.skeleton)
        if spec.supersession is not None:
            table["supersession"] = {
                "forward": spec.supersession.forward,
                "back": spec.supersession.back,
                "status": spec.supersession.status,
            }
        if spec.structure is not None:
            s = spec.structure
            table["structure"] = {
                "sections": list(s.sections),
                "table_in": s.table_in,
                "columns": list(s.columns),
                "key_column": s.key_column,
                "body_column": s.body_column,
                "scanned_columns": list(s.scanned_columns),
                "max_rows": s.max_rows,
                "max_cell": s.max_cell,
                "max_chars": s.max_chars,
            }
        out["types"][name] = table
    return out


def from_dict(data: dict[str, Any], preset: str = "custom", settings: Settings = SETTINGS) -> Registry:
    """Construct a registry from plain data -- the inverse of `to_dict`, and the constructor the 0.2
    loader calls once it has merged a config over its preset. Strict: an unknown key is an error,
    since a typo that validated as nothing would be exactly the silent failure this tool exists to
    remove."""
    anchors: dict[str, AnchorField] = {}
    for name, table in (data.get("anchors") or {}).items():
        _only(table, {"contents", "resolves"}, f"anchors.{name}")
        anchors[name] = AnchorField(name, str(table.get("contents", "")), tuple(table.get("resolves", ())))
    types: dict[str, DocType] = {}
    known = _FACETS - {"name", "requires"} | set(anchors)
    for name, table in (data.get("types") or {}).items():
        _only(table, known, f"types.{name}")
        kwargs: dict[str, Any] = {"name": name}
        for key in ("serves", "voice", "mutability", "description"):
            if key in table:
                kwargs[key] = str(table[key])
        for key in ("enabled", "numbered", "root_required", "additive", "append_only"):
            if key in table:
                kwargs[key] = bool(table[key])
        for key in ("default_status", "folder", "fixed_name", "requires_from"):
            if key in table:
                kwargs[key] = table[key]
        for key in ("statuses", "skeleton"):
            if key in table:
                kwargs[key] = tuple(table[key])
        kwargs["requires"] = tuple(a for a in anchors if table.get(a))
        if "supersession" in table:
            kwargs["supersession"] = Supersession(**table["supersession"])
        if "structure" in table:
            s = dict(table["structure"])
            for key in ("sections", "columns", "scanned_columns"):
                s[key] = tuple(s[key])
            kwargs["structure"] = Structure(**s)
        for required in ("serves", "voice", "mutability"):
            kwargs.setdefault(required, "")
        types[name] = DocType(**kwargs)
    return Registry(preset, anchors, types, settings)


def _only(table: dict[str, Any], allowed: set[str], where: str) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise ValueError(f"{where}: unknown key(s) {unknown}; allowed: {sorted(allowed)}")


def to_toml(registry: Registry) -> str:
    """The registry as TOML. Hand-rolled for the few shapes the schema uses -- strings, booleans,
    integers, string lists, nested tables -- because the writer must run at runtime and the
    dependency policy admits no runtime dependency for it."""
    data = to_dict(registry)
    lines: list[str] = [
        "# The effective doc-marshal registry, as configuration. `doc-marshal info --dump-toml`.",
        "# Configuration is read from 0.2; this is the schema it will take.",
        "",
        f"extends = {_toml_value(data['extends'])}",
    ]
    for section in ("anchors", "types"):
        for name, table in data[section].items():
            lines += ["", f"[{section}.{_toml_key(name)}]"]
            nested = {k: v for k, v in table.items() if isinstance(v, dict)}
            for key, value in table.items():
                if key not in nested:
                    lines.append(f"{_toml_key(key)} = {_toml_value(value)}")
            for key, sub in nested.items():
                lines += ["", f"[{section}.{_toml_key(name)}.{_toml_key(key)}]"]
                for k, v in sub.items():
                    lines.append(f"{_toml_key(k)} = {_toml_value(v)}")
    return "\n".join(lines) + "\n"


def _toml_key(key: str) -> str:
    return key if key.replace("_", "").replace("-", "").isalnum() else _toml_str(key)


def _toml_str(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")
    )
    return f'"{escaped}"'


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return _toml_str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    raise TypeError(f"cannot serialize {type(value).__name__} to TOML")


def with_settings(registry: Registry, settings: Settings) -> Registry:
    """The same registry bound to different Tier 3 constants."""
    return replace(registry, settings=settings)
