"""`doc-marshal init`: mark a directory as the docs root and write the integration files.

    doc-marshal init                    # docs/
    doc-marshal init agent-docs         # any other directory
    doc-marshal init --claude-code      # CLAUDE.md instead of AGENTS.md, plus the permission entry

This is the command that makes a repository legible to the tool, not a convenience. It writes:

- the marker, `.doc-marshal.toml`, empty -- location rather than configuration in 0.1;
- the root `context` note, because that type is `root_required` and `check --all` errors without it;
- the generated index, so the tree validates from its first minute;
- one small agent-memory pointer file, `AGENTS.md` (or `CLAUDE.md`), inside the docs root. A
  pointer to `doc-marshal info`, never a copy of the rules, so it cannot drift.

It warns, rather than refusing, when the target looks like a published site or holds markdown
without frontmatter: adopting the convention on an existing tree is a legitimate thing to do, and
the marker makes the intent explicit.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import load_registry
from .index import index_state, render
from .new import frontmatter_lines, render_note
from .ontology import Registry
from .paths import (
    DocMarshalError,
    find_markers,
    git_toplevel,
    rel_to,
    split_frontmatter,
)
from .settings import SETTINGS, Settings

SITE_FILES = ("conf.py", "mkdocs.yml", "_config.yml", "book.toml")
SITE_GLOBS = ("docusaurus.config.*",)

PERMISSION = "Bash(doc-marshal:*)"


def site_markers(target: Path) -> list[str]:
    """Files that mark a published-site tree: Sphinx, MkDocs, Jekyll, mdBook, Docusaurus."""
    found = [name for name in SITE_FILES if (target / name).is_file()]
    for pattern in SITE_GLOBS:
        found += [p.name for p in target.glob(pattern) if p.is_file()]
    return found


def frontmatterless(target: Path, settings: Settings) -> list[Path]:
    """Markdown files under the target that carry no frontmatter and would fail as notes."""
    hits: list[Path] = []
    for path in sorted(target.rglob("*.md")):
        if settings.excluded_dirs.intersection(path.relative_to(target).parts):
            continue
        if path.name in settings.excluded_names:
            continue
        try:
            block, _ = split_frontmatter(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        if block is None:
            hits.append(path)
    return hits


def pointer_text(docs_label: str, claude_code: bool) -> str:
    plugin = (
        "\nWith the doc-marshal Claude Code plugin installed, every note you write is validated as "
        "you write it and this tree's index and vocabulary are injected at session start.\n"
        if claude_code
        else ""
    )
    return f"""# {docs_label}

This directory is a doc-marshal docs root: a tree of typed markdown notes whose primary reader is a
coding agent, validated by `doc-marshal check`. The rules are not copied here -- they ship in the
tool, so they always match the installed version:

```bash
doc-marshal info                 # the note types and their anchors, one line each
doc-marshal info <type>          # one type in full: what it serves, how it reads, its skeleton
doc-marshal info --conventions   # every rule for this tree
doc-marshal info --process       # how to reflect a finished code change in these docs
```

Working here:

- **Finding a doc**: `INDEX.md` is the routing surface, one generated line per note with its type
  and summary. Read it rather than listing the tree. Never edit it; `doc-marshal index` regenerates it.
- **Naming a thing**: `CONTEXT.md` is the shared vocabulary. Write in its terms, in docs and in code.
- **Writing a note**: `doc-marshal new <type> <path> --summary "..."` scaffolds one the validator
  accepts. Then `doc-marshal check <path>`.
- **After a code change**: `doc-marshal affected` lists the notes anchored to what changed. Follow
  `doc-marshal info --process` to update them.
{plugin}"""


def merge_permission(settings_path: Path) -> bool:
    """Add the Bash permission to `.claude/settings.json`, creating it if needed. True when changed."""
    data: dict = {}
    if settings_path.is_file():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DocMarshalError(f"{settings_path} is not valid JSON -- {exc}") from exc
        if not isinstance(data, dict):
            raise DocMarshalError(f"{settings_path} does not hold a JSON object")
    permissions = data.setdefault("permissions", {})
    allow = permissions.setdefault("allow", [])
    if PERMISSION in allow:
        return False
    allow.append(PERMISSION)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return True


def scaffold_context(target: Path, registry: Registry, repo_name: str) -> Path | None:
    """The root context note, if the registry has a root-required fixed-name type and it is absent."""
    for spec in registry.enabled.values():
        if not spec.root_required or spec.fixed_name is None:
            continue
        path = target / spec.fixed_name
        if path.exists():
            return None
        from datetime import date

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
        help="write CLAUDE.md instead of AGENTS.md, and allow `doc-marshal` in .claude/settings.json",
    )
    args = parser.parse_args(argv)
    settings = SETTINGS

    cwd = Path.cwd().resolve()
    toplevel = git_toplevel(cwd)
    repo_root = toplevel or cwd
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
        marker.write_text("", encoding="utf-8")
        written.append(f"{label}/{settings.marker_name}  (the marker; empty -- configuration arrives in 0.2)")
    else:
        print(f"{label}/{settings.marker_name} already exists -- filling in whatever else is missing")

    registry = load_registry(target, settings)
    context = scaffold_context(target, registry, repo_root.name)
    if context is not None:
        written.append(f"{label}/{context.name}  (the shared vocabulary -- fill in the terms this project uses)")

    pointer_name = "CLAUDE.md" if args.claude_code else "AGENTS.md"
    pointer = target / pointer_name
    if not pointer.exists():
        pointer.write_text(pointer_text(label, args.claude_code), encoding="utf-8")
        written.append(f"{label}/{pointer_name}  (a pointer to `doc-marshal info`, not a copy of the rules)")

    state = index_state(target, registry)
    index = target / settings.index_name
    if state.notes and not state.problems:
        if state.stale:
            index.write_text(render(state.notes), encoding="utf-8")
            written.append(f"{label}/{settings.index_name}  (generated -- {len(state.notes)} note(s))")
    elif state.problems:
        print(
            f"warn:  {settings.index_name} not generated -- these notes cannot be indexed yet:\n  "
            + "\n  ".join(state.problems),
            file=sys.stderr,
        )

    if args.claude_code:
        if merge_permission(repo_root / ".claude" / "settings.json"):
            written.append(f".claude/settings.json  (allowed {PERMISSION})")

    if written:
        print("wrote:")
        for line in written:
            print(f"  {line}")
    else:
        print(f"{label}/ is already initialised -- nothing to write")

    print(
        f"""
next:
  doc-marshal check --all            # validates {label}/ ({__version__})
  doc-marshal info --process         # how docs are updated after a code change

  Pre-commit, in .pre-commit-config.yaml:
    - repo: https://github.com/rootdrew27/doc-marshal
      rev: v{__version__}
      hooks:
        - id: doc-marshal-check
        - id: doc-marshal-index

  CI, on every pull request (no paths: filter -- anchors break in the change that renames the code):
    uvx doc-marshal=={__version__} check --all
    uvx doc-marshal=={__version__} index --check
    uvx doc-marshal=={__version__} affected --range "${{{{ github.event.pull_request.base.sha }}}}..HEAD" --format github
"""
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
