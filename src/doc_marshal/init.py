"""`doc-marshal init`: mark a directory as the docs root and write the integration files.

    doc-marshal init                    # docs/
    doc-marshal init agent-docs         # any other directory
    doc-marshal init --claude-code      # CLAUDE.md instead of AGENTS.md, imported from the root

This is the command that makes a repository legible to the tool, not a convenience. It writes:

- the marker, `.doc-marshal.toml`, a comment and no keys -- location, not configuration, until a
  later release reads it;
- the root `nomenclature` note, because that type is `root_required` and `check --all` errors without it;
- the generated index, so the tree validates from its first minute;
- one small agent-memory pointer file, `AGENTS.md` (or `CLAUDE.md`), inside the docs root. It
  says what the tree, its commands and its two special files are for -- a pointer to
  `doc-marshal info`, never a copy of the rules, so it cannot drift.

With `--claude-code` it also puts the pointer in every session: one `@<docs root>/CLAUDE.md`
import line in the repository's root `CLAUDE.md`, which Claude Code reads at start. A nested
memory file on its own is loaded only once a session reads under that directory, so without the
line a session that never opens the docs never learns they exist. Other harnesses have no import
syntax, so plain `init` prints the reference line for the root `AGENTS.md` and writes nothing there.

It warns, rather than refusing, when the target looks like a published site or holds markdown
without frontmatter: adopting the convention on an existing tree is a legitimate thing to do, and
the marker makes the intent explicit.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from . import __version__
from .config import load_registry
from .index import index_state, plural, render
from .new import frontmatter_lines, render_note
from .ontology import Registry
from .paths import (
    DocMarshalError,
    cwd_repo,
    find_markers,
    iter_notes,
    rel_to,
    split_frontmatter,
)
from .settings import SETTINGS, Settings

SITE_FILES = ("conf.py", "mkdocs.yml", "_config.yml", "book.toml")
SITE_GLOBS = ("docusaurus.config.*",)

# What `init` writes into the marker. The one person who will ever open this file is about to add a
# key to it, so the blast radius of doing that is stated where they will read it.
MARKER_TEXT = """\
# doc-marshal docs root. The file marks the directory by existing.
# Configuration arrives in a later release; until then any key here makes every doc-marshal command exit 2.
"""

# Every spelling of the engine an agent might run: on PATH, through uv, and the project's own
# virtualenv. A permission for the bare name alone never matches the two forms a session actually
# uses when the package is a project dependency, and a non-interactive session cannot ask.
PERMISSIONS = ("Bash(doc-marshal:*)", "Bash(uv run doc-marshal:*)", "Bash(.venv/bin/doc-marshal:*)")


def site_markers(target: Path) -> list[str]:
    """Files that mark a published-site tree: Sphinx, MkDocs, Jekyll, mdBook, Docusaurus."""
    found = [name for name in SITE_FILES if (target / name).is_file()]
    for pattern in SITE_GLOBS:
        found += [p.name for p in target.glob(pattern) if p.is_file()]
    return found


def frontmatterless(target: Path, settings: Settings) -> list[Path]:
    """Notes under the target that carry no frontmatter and would fail as notes."""
    hits: list[Path] = []
    for path in iter_notes(target, settings):
        try:
            block, _ = split_frontmatter(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        if block is None:
            hits.append(path)
    return hits


def pointer_text(docs_label: str, settings: Settings, registry: Registry) -> str:
    """The pointer file: what the tree, its commands and its two special files are for.

    Descriptive on purpose. With `--claude-code` this is imported into every session, so it says
    what exists and what each thing is for, and leaves how to use them to `doc-marshal info`,
    which is versioned with the engine. No heading: as an import it is a fragment of the root
    file, not a document.
    """
    index = settings.index_name
    lines = [
        f"`{docs_label}/` is a doc-marshal docs tree: typed markdown notes whose primary reader is a coding",
        "agent. The rules ship in the tool, not in this file.",
        "",
        "```bash",
        "doc-marshal info                 # the note types and their anchors, one line each",
        "doc-marshal info <type>          # one type in full: what it serves, how it reads, its skeleton",
        "doc-marshal info --rules         # every rule for this tree",
        "doc-marshal info --process       # how these docs are written: for a change, a subject, or a clean-up",
        "doc-marshal check <path>         # validates a note against the rules; --all sweeps the tree",
        "doc-marshal new <type> <path>    # scaffolds a note with the frontmatter and sections its type requires",
        "doc-marshal affected             # the notes anchored to code a change touched",
        f"doc-marshal index                # regenerates {index}",
        "```",
        "",
        f"- `{index}` -- generated routing surface: one line per note with its type and summary.",
    ]
    for spec in registry.root_notes:
        lines.append(f"- `{spec.fixed_name}` -- the shared vocabulary for docs and code, and the aliases it rules out.")
    return "\n".join(lines) + "\n"


def import_line(docs_label: str, pointer_name: str) -> str:
    """The Claude Code memory import that pulls the docs-root pointer into every session."""
    return f"@{docs_label}/{pointer_name}"


def has_import(root_file: Path, line: str) -> bool:
    """Whether the root memory file already carries the import line."""
    return root_file.is_file() and any(
        existing.strip() == line for existing in root_file.read_text(encoding="utf-8").splitlines()
    )


def merge_import(root_file: Path, line: str) -> bool:
    """Put `line` in the repository's root memory file: create the file with it, append it after
    a blank line, or leave the file alone when the line is already there. True when it wrote."""
    if not root_file.exists():
        root_file.write_text(f"{line}\n", encoding="utf-8")
        return True
    if has_import(root_file, line):
        return False
    text = root_file.read_text(encoding="utf-8")
    if text and not text.endswith("\n"):
        text += "\n"
    if text and not text.endswith("\n\n"):
        text += "\n"
    root_file.write_text(f"{text}{line}\n", encoding="utf-8")
    return True


def merge_permission(settings_path: Path) -> bool:
    """Add the Bash permissions to `.claude/settings.json`, creating it if needed. True when changed."""
    data: dict[str, Any] = {}
    if settings_path.is_file():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DocMarshalError(f"{settings_path} is not valid JSON -- {exc}") from exc
        if not isinstance(data, dict):
            raise DocMarshalError(f"{settings_path} does not hold a JSON object")
    permissions = data.setdefault("permissions", {})
    allow = permissions.setdefault("allow", [])
    missing = [p for p in PERMISSIONS if p not in allow]
    if not missing:
        return False
    allow.extend(missing)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return True


def scaffold_nomenclature(target: Path, registry: Registry, repo_name: str) -> Path | None:
    """The root nomenclature note, if the registry has a root-required fixed-name type and it is absent."""
    for spec in registry.root_notes:
        path = spec.fixed_path(target)
        if path.exists():
            return None
        today = date.today().isoformat()
        summary = (
            "The project's shared terminology -- one word per concept, the aliases ruled out, and "
            "the live ambiguities. Emitted into every session."
        )
        meta = frontmatter_lines(spec.name, summary, today)
        path.write_text(render_note(f"{repo_name} shared vocabulary", meta, spec, today), encoding="utf-8")
        return path
    return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="doc-marshal init", description="Mark a directory as the docs root and wire it up."
    )
    parser.add_argument(
        "path", nargs="?", help=f"the docs root to mark (default: {SETTINGS.default_docs_dir}/ at the repo root)"
    )
    parser.add_argument(
        "--claude-code",
        action="store_true",
        help="write CLAUDE.md instead of AGENTS.md, import it from the root CLAUDE.md, and allow "
        "`doc-marshal` in .claude/settings.json",
    )
    args = parser.parse_args(argv)
    settings = SETTINGS

    cwd, repo_root, toplevel = cwd_repo()
    given = Path(args.path) if args.path else Path(settings.default_docs_dir)
    target = (given if given.is_absolute() else repo_root / given).resolve()
    if not target.is_relative_to(repo_root):
        raise DocMarshalError(f"the docs root must lie inside the repository ({repo_root}): {target}")
    if target == repo_root:
        raise DocMarshalError("the docs root must be a directory inside the repository, not the repository itself")
    label = rel_to(target, repo_root).as_posix()

    others = [m for m in find_markers(repo_root, cwd, settings, stop_at=toplevel) if m.parent != target]
    if others:
        listing = ", ".join(f"{rel_to(m.parent, repo_root)}/" for m in others)
        raise DocMarshalError(
            f"a {settings.marker_name} marker already exists at {listing}, and one repository has "
            "one docs root. Remove it first if the tree is moving."
        )

    warnings: list[str] = []
    if target.is_dir():
        found = site_markers(target)
        if found:
            warnings.append(
                f"{label}/ looks like a published documentation site -- it holds "
                f"{', '.join(found)}. doc-marshal will validate every markdown file under it as a "
                "note. If the site is human-authored, put the docs root somewhere else: "
                "`doc-marshal init <other path>`."
            )
        loose = frontmatterless(target, settings)
        if loose:
            sample = ", ".join(rel_to(p, repo_root).as_posix() for p in loose[:5])
            more = f" and {len(loose) - 5} more" if len(loose) > 5 else ""
            warnings.append(
                f"{label}/ holds {len(loose)} markdown file(s) without frontmatter, which "
                f"`doc-marshal check --all` will report as errors: {sample}{more}. Add frontmatter "
                "to each, or move them out."
            )
    for warning in warnings:
        print(f"warn:  {warning}", file=sys.stderr)

    written: list[str] = []
    target.mkdir(parents=True, exist_ok=True)
    marker = target / settings.marker_name
    if not marker.exists():
        marker.write_text(MARKER_TEXT, encoding="utf-8")
        written.append(f"{label}/{settings.marker_name}  (the marker; holds no keys until configuration lands)")
    else:
        print(f"{label}/{settings.marker_name} already exists -- filling in whatever else is missing")

    registry = load_registry(target, settings)
    nomenclature = scaffold_nomenclature(target, registry, repo_root.name)
    if nomenclature is not None:
        written.append(f"{label}/{nomenclature.name}  (the shared vocabulary -- fill in the terms this project uses)")

    pointer_name = "CLAUDE.md" if args.claude_code else "AGENTS.md"
    pointer = target / pointer_name
    if not pointer.exists():
        pointer.write_text(pointer_text(label, settings, registry), encoding="utf-8")
        written.append(f"{label}/{pointer_name}  (a pointer to `doc-marshal info`, not a copy of the rules)")
    line = import_line(label, pointer_name)
    if args.claude_code and merge_import(repo_root / pointer_name, line):
        written.append(f"{pointer_name}  (imports {label}/{pointer_name} into every session: `{line}`)")

    state = index_state(target, registry)
    if state.problems:
        print(
            f"warn:  {settings.index_name} not generated -- these notes cannot be indexed yet:\n  "
            + "\n  ".join(state.problems),
            file=sys.stderr,
        )
    elif state.notes and state.stale:
        (target / settings.index_name).write_text(render(state.notes), encoding="utf-8")
        written.append(f"{label}/{settings.index_name}  (generated -- {len(state.notes)} {plural(len(state.notes))})")

    if args.claude_code and merge_permission(repo_root / ".claude" / "settings.json"):
        written.append(f".claude/settings.json  (allowed {', '.join(PERMISSIONS)})")

    if written:
        print("wrote:")
        for line in written:
            print(f"  {line}")
    else:
        print(f"{label}/ is already initialised -- nothing to write")

    reference = (
        ""
        if args.claude_code
        else f"""
  Tell agents the tree exists -- one line in the root {pointer_name}:
    Documentation is a doc-marshal docs tree; {label}/{pointer_name} says what it is for.
"""
    )
    print(
        f"""
next:
  doc-marshal check --all            # validates {label}/ ({__version__})
  doc-marshal info --process         # how the docs are written, staged
{reference}
  Pre-commit, in .pre-commit-config.yaml:
    - repo: https://github.com/rootdrew27/doc-marshal
      rev: v{__version__}
      hooks:
        - id: doc-marshal-check
        - id: doc-marshal-index

  CI, on every pull request (no paths: filter -- anchors break in the change that renames the code):
    uvx doc-marshal=={__version__} check --all --format github
    uvx doc-marshal=={__version__} index --check
    uvx doc-marshal=={__version__} affected --range "${{{{ github.event.pull_request.base.sha }}}}..HEAD" --format github
"""
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
