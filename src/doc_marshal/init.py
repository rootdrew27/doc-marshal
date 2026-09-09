"""`doc-marshal init`: mark a directory as the docs tree and write the integration files.

    doc-marshal init                    # docs/
    doc-marshal init agent-docs         # any other directory
    doc-marshal init --claude-code      # CLAUDE.md instead of AGENTS.md, imported from the root
    doc-marshal init --pre-commit --ci  # wire the commit and pull-request integrations

This is the command that makes a repository legible to the tool, not a convenience. It writes:

- the config, `.doc-marshal.toml`, a comment and no keys -- location, not configuration, until a
  later release reads it;
- the root `nomenclature` note, because that type is `root_required` and `check --all` errors without it;
- the generated index, so the tree validates from its first minute;
- one small agent-memory pointer file, `AGENTS.md` (or `CLAUDE.md`), inside the docs tree. It
  says what the tree, its commands and its two special files are for -- a pointer to
  `doc-marshal info`, never a copy of the policies, so it cannot drift.

With `--claude-code` it also puts the pointer in every session: one `@<docs tree>/CLAUDE.md`
import line in the repository's root `CLAUDE.md`, which Claude Code reads at start. A nested
memory file on its own is loaded only once a session reads under that directory, so without the
line a session that never opens the docs never learns they exist. Other harnesses have no import
syntax, so plain `init` prints the reference line for the root `AGENTS.md` and writes nothing there.

`--claude-code` also installs the plugin, through the `claude` CLI, at project scope -- the
enablement lands in the repository's own `.claude/settings.json`, so the hooks arrive with a clone
rather than with each person who remembers to run `/plugin`. Both commands are idempotent and the
engine never edits that key itself: Claude Code owns the shape of its settings file. With no
`claude` on PATH, or with `--no-plugin`, the two commands are printed instead.

`--pre-commit` and `--ci` write the other two integrations (see docs/integrations.md), at the
version this engine is, rather than printing them for a human to paste at whichever version they
read about. The wiring belongs to the engine because it is versioned with the policies it wires,
and because it reaches the pre-commit, CI, Codex and Cursor users who never install the plugin.
Both files are generated in `integrate`, which is also where `doctor` reads them back.

It warns, rather than refusing, when the target looks like a published site or holds markdown
without frontmatter: adopting the convention on an existing tree is a legitimate thing to do, and
the config makes the intent explicit.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import textwrap
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

from . import __version__
from .config import load_profile
from .discovery import cwd_repo, find_configs
from .errors import DocMarshalError
from .frontmatter import split_frontmatter
from .index import index_state, plural, render
from .integrate import CI_FILE, WORKFLOWS, Written, has_hook, writable, write_ci, write_precommit
from .new import frontmatter_lines, render_note
from .ontology import Profile
from .paths import iter_notes, rel_to
from .settings import SETTINGS, Settings

SITE_FILES = ("conf.py", "mkdocs.yml", "_config.yml", "book.toml")
SITE_GLOBS = ("docusaurus.config.*",)

# What `init` writes into the config. The one person who will ever open this file is about to add
# a key to it, so the blast radius of doing that is stated where they will read it.
CONFIG_TEXT = """\
# doc-marshal docs tree config. The file marks the directory by existing.
# The profile's adjustments arrive in a later release; until then any key here makes every doc-marshal command exit 2.
"""

# Every spelling of the engine an agent might run: on PATH, through uv, and the project's own
# virtualenv. A permission for the bare name alone never matches the two forms a session actually
# uses when the package is a project dependency, and a non-interactive session cannot ask.
PERMISSIONS = ("Bash(doc-marshal:*)", "Bash(uv run doc-marshal:*)", "Bash(.venv/bin/doc-marshal:*)")

# The plugin ships from this repository's own marketplace file, so one source declares both. Project
# scope on purpose: the plugin is a property of the repository -- these docs are validated as they
# are written -- rather than of the person who cloned it.
MARKETPLACE = "rootdrew27/doc-marshal"
PLUGIN = "doc-marshal@doc-marshal"
PLUGIN_SCOPE = "project"


def width() -> int:
    """The column to wrap prose at: the terminal's, capped so a maximised window does not produce
    200-column paragraphs, floored so a narrow one still breaks somewhere readable."""
    return max(60, min(shutil.get_terminal_size((100, 24)).columns, 100))


def columns(rows: Sequence[tuple[str, str]], indent: str = "  ") -> list[str]:
    """Rows as two aligned columns -- the path, then what it is for -- with the second column
    wrapped under itself when the pair is wider than the terminal."""
    left = max(len(path) for path, _ in rows)
    lines: list[str] = []
    for path, does in rows:
        head = f"{indent}{path.ljust(left)}  "
        lines += textwrap.wrap(does, width=width(), initial_indent=head, subsequent_indent=" " * len(head))
    return lines


def numbered(steps: Sequence[str], indent: str = "  ") -> list[str]:
    """Steps as a wrapped numbered list. A step's later lines are text to paste -- a memory line, a
    command -- so they are printed as they are, under the hanging indent."""
    lines: list[str] = []
    for number, step in enumerate(steps, 1):
        head = f"{indent}{number}. "
        first, *rest = step.splitlines()
        lines += textwrap.wrap(first, width=width(), initial_indent=head, subsequent_indent=" " * len(head))
        lines += [f"{' ' * len(head)}  {line.strip()}" for line in rest]
    return lines


def warn(text: str) -> None:
    """A warning on stderr, wrapped under its own label. Later lines are already a list -- the
    notes that could not be indexed -- and keep their own line each."""
    first, *rest = text.splitlines()
    print(
        "\n".join(textwrap.wrap(first, width=width(), initial_indent="warn:  ", subsequent_indent="       ")),
        file=sys.stderr,
    )
    for line in rest:
        print(f"       {line.strip()}", file=sys.stderr)


def paragraph(text: str, indent: str = "  ") -> str:
    """A writer's note, wrapped. A line that arrives indented is a block to paste -- the pre-commit
    entry, the CI steps -- and is never reflowed."""
    lines: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            lines.append("")
        elif line[:1].isspace():
            lines.append(f"{indent}{line}")
        else:
            lines += textwrap.wrap(line, width=width(), initial_indent=indent, subsequent_indent=indent)
    return "\n".join(lines)


def site_files(target: Path) -> list[str]:
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


def pointer_text(docs_label: str, settings: Settings, profile: Profile) -> str:
    """The pointer file: what the tree, its commands and its two special files are for.

    Descriptive on purpose. With `--claude-code` this is imported into every session, so it says
    what exists and what each thing is for, and leaves how to use them to `doc-marshal info`,
    which is versioned with the engine. No heading: as an import it is a fragment of the root
    file, not a document.
    """
    index = settings.index_name
    lines = [
        f"`{docs_label}/` is a doc-marshal docs tree: typed markdown notes whose primary reader is a coding",
        "agent. The policies ship in the tool, not in this file.",
        "",
        "```bash",
        "doc-marshal info                 # the note types and their anchors, one line each",
        "doc-marshal info <type>          # one type in full: what it serves, how it reads, its template",
        "doc-marshal info --policies      # every policy for this tree",
        "doc-marshal info --marshalling   # how these docs are written: for a change, a subject, or a clean-up",
        "doc-marshal check <path>         # validates a note against the policies; --all sweeps the tree",
        "doc-marshal new <type> <path>    # scaffolds a note with the frontmatter and sections its type requires",
        "doc-marshal drifted              # the notes anchored to code a change touched",
        f"doc-marshal index                # regenerates {index}",
        "```",
        "",
        f"- `{index}` -- generated routing surface: one line per note with its type and summary.",
    ]
    for spec in profile.root_notes:
        lines.append(
            f"- `{spec.reserved_filename}` -- the shared vocabulary for docs and code, and the aliases it rules out."
        )
    return "\n".join(lines) + "\n"


def import_line(docs_label: str, pointer_name: str) -> str:
    """The Claude Code memory import that pulls the docs-tree pointer into every session."""
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


def scaffold_nomenclature(target: Path, profile: Profile, repo_name: str) -> Path | None:
    """The root nomenclature note, if the profile has a root-required reserved-filename type and it is absent."""
    for spec in profile.root_notes:
        path = spec.reserved_path(target)
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


def plugin_commands() -> list[list[str]]:
    """The two commands that put the plugin in a repository: declare the marketplace, install from
    it. `--yes` because `init` may run with no terminal to answer a prompt."""
    return [
        ["claude", "plugin", "marketplace", "add", MARKETPLACE, "--scope", PLUGIN_SCOPE],
        ["claude", "plugin", "install", PLUGIN, "--scope", PLUGIN_SCOPE, "--yes"],
    ]


def install_plugin(repo_root: Path) -> str:
    """Install the Claude Code plugin, and report what happened in one paragraph.

    Never fatal. `init` marks a docs tree, and a tree with no plugin is validated by every other
    integration -- so a missing `claude`, an offline clone or a Claude Code that changed its CLI
    costs the user the two commands to run by hand, not the initialisation.
    """
    printable = "\n".join(f"  {' '.join(command)}" for command in plugin_commands())
    if shutil.which("claude") is None:
        return (
            f"no `claude` on PATH, so the plugin was not installed. It validates each note as it is "
            f"written and hands every session the briefing. With Claude Code installed:\n\n{printable}"
        )
    for command in plugin_commands():
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=180, cwd=str(repo_root), check=False
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return f"`{' '.join(command)}` did not run ({exc}). The plugin is not installed. To finish by hand:\n\n{printable}"
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            return (
                f"`{' '.join(command)}` exited {result.returncode}"
                + (f" -- {detail[-1]}" if detail else "")
                + f". The plugin is not installed. To finish by hand:\n\n{printable}"
            )
    return (
        f"{PLUGIN} installed at {PLUGIN_SCOPE} scope, so .claude/settings.json enables it for "
        "everyone who clones this repository. It validates each note as it is written and hands "
        "every session the briefing. A running Claude Code picks it up on the next session."
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="doc-marshal init", description="Mark a directory as the docs tree and wire it up."
    )
    parser.add_argument(
        "path", nargs="?", help=f"the docs tree to mark (default: {SETTINGS.default_docs_dir}/ at the repo root)"
    )
    parser.add_argument(
        "--claude-code",
        action="store_true",
        help="write CLAUDE.md instead of AGENTS.md, import it from the root CLAUDE.md, allow "
        "`doc-marshal` in .claude/settings.json, and install the plugin with the `claude` CLI",
    )
    parser.add_argument(
        "--no-plugin",
        action="store_true",
        help="with --claude-code, do not install the plugin -- print the two `claude plugin` commands instead",
    )
    parser.add_argument(
        "--pre-commit",
        action="store_true",
        help="write .pre-commit-config.yaml, or print the block to paste into the one that exists",
    )
    parser.add_argument("--ci", action="store_true", help="write .github/workflows/docs.yml, pinned to this version")
    parser.add_argument(
        "--pin",
        metavar="X.Y.Z",
        help="the version the integration files name, when it is not this engine's -- a dev "
        "checkout has no tag for a `rev:` to resolve, so it names a released version instead",
    )
    args = parser.parse_args(argv)
    settings = SETTINGS

    cwd, repo_root, toplevel = cwd_repo()
    given = Path(args.path) if args.path else Path(settings.default_docs_dir)
    target = (given if given.is_absolute() else repo_root / given).resolve()
    if not target.is_relative_to(repo_root):
        raise DocMarshalError(f"the docs tree must lie inside the repository ({repo_root}): {target}")
    if target == repo_root:
        raise DocMarshalError("the docs tree must be a directory inside the repository, not the repository itself")
    label = rel_to(target, repo_root).as_posix()

    others = [m for m in find_configs(repo_root, cwd, settings, stop_at=toplevel) if m.parent != target]
    if others:
        listing = ", ".join(f"{rel_to(m.parent, repo_root)}/" for m in others)
        raise DocMarshalError(
            f"a {settings.config_name} config already exists at {listing}, and one repository has "
            "one docs tree. Remove it first if the tree is moving."
        )

    warnings: list[str] = []
    if target.is_dir():
        found = site_files(target)
        if found:
            warnings.append(
                f"{label}/ looks like a published documentation site -- it holds "
                f"{', '.join(found)}. doc-marshal will validate every markdown file under it as a "
                "note. If the site is human-authored, put the docs tree somewhere else: "
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
        warn(warning)

    created: list[Written] = []
    target.mkdir(parents=True, exist_ok=True)
    config = target / settings.config_name
    if not config.exists():
        config.write_text(CONFIG_TEXT, encoding="utf-8")
        created.append(
            Written(f"{label}/{settings.config_name}", "marks the tree; holds no keys until configuration lands")
        )

    profile = load_profile(target, settings)
    nomenclature = scaffold_nomenclature(target, profile, repo_root.name)
    if nomenclature is not None:
        created.append(Written(f"{label}/{nomenclature.name}", "the shared vocabulary -- one row per term, to fill in"))

    pointer_name = "CLAUDE.md" if args.claude_code else "AGENTS.md"
    pointer = target / pointer_name
    if not pointer.exists():
        pointer.write_text(pointer_text(label, settings, profile), encoding="utf-8")
        created.append(Written(f"{label}/{pointer_name}", "points at `doc-marshal info`; never a copy of the policies"))
    line = import_line(label, pointer_name)
    if args.claude_code and merge_import(repo_root / pointer_name, line):
        created.append(Written(pointer_name, f"imports {label}/{pointer_name} into every session (`{line}`)"))

    state = index_state(target, profile)
    if state.problems:
        warn(f"{settings.index_name} not generated -- these notes cannot be indexed yet:\n" + "\n".join(state.problems))
    elif state.notes and state.stale:
        (target / settings.index_name).write_text(render(state.notes), encoding="utf-8")
        created.append(
            Written(f"{label}/{settings.index_name}", f"generated -- {len(state.notes)} {plural(len(state.notes))}")
        )

    if args.claude_code and merge_permission(repo_root / ".claude" / "settings.json"):
        created.append(Written(".claude/settings.json", "allows the three spellings of `doc-marshal` a session runs"))

    # One answer to "which version may these files name", shared by the writers below and by the
    # advice printed further down: a version too unsafe to write is too unsafe to print as a
    # snippet to paste, which is the same broken `rev:` arriving by hand instead.
    notes: list[str] = []
    pin = writable(args.pin)
    for wanted, writer in ((args.pre_commit, write_precommit), (args.ci, write_ci)):
        if not wanted:
            continue
        outcome = writer(repo_root, pin)
        if outcome.written:
            created.append(outcome.written)
        if outcome.note:
            notes.append(outcome.note)

    # After the permissions merge: Claude Code rewrites the same settings file, and it owns the
    # shape of the keys it writes.
    plugin_note: str | None = None
    if args.claude_code:
        plugin_note = (
            "--no-plugin, so the plugin was not installed. The two commands, whenever you want "
            "it:\n\n" + "\n".join(f"  {' '.join(command)}" for command in plugin_commands())
            if args.no_plugin
            else install_plugin(repo_root)
        )

    if created:
        print(f"{label}/ is a doc-marshal docs tree, checked by doc-marshal {__version__}.\n")
        print("created:")
        print("\n".join(columns(created)))
    elif not notes:
        print(f"{label}/ is already a doc-marshal docs tree -- nothing left to write")
    if notes:
        print("\nnote:")
        print("\n\n".join(paragraph(note) for note in notes))
    if plugin_note is not None:
        print(f"\nplugin:\n{paragraph(plugin_note)}")

    steps: list[str] = []
    if nomenclature is not None:
        steps.append(
            f"Fill in {label}/{nomenclature.name}: one row per term this project uses "
            "inconsistently. Every session is handed this file."
        )
    if not args.claude_code:
        steps.append(
            f"Add one line to the root {pointer_name}, so a session that never opens {label}/ "
            f"still learns the tree exists:\n"
            f"Documentation is a doc-marshal docs tree; {label}/{pointer_name} says what it is for."
        )
    steps.append("Validate the tree:\ndoc-marshal check --all")
    steps.append("Read how these docs get written:\ndoc-marshal info --marshalling")
    print("\nnext:")
    print("\n".join(numbered(steps)))

    # The integrations the flags did not ask for. Named, not printed: a config file nobody asked
    # for is noise in the terminal, and the flag writes it correctly at a version this engine
    # resolves, which a pasted snippet does not.
    available: list[Written] = []
    if not args.pre_commit and not has_hook(repo_root):
        available.append(
            Written("doc-marshal init --pre-commit", "check the staged notes, and the index, at every commit")
        )
    if not args.ci and not (repo_root / WORKFLOWS / CI_FILE).is_file():
        available.append(
            Written("doc-marshal init --ci", "check --all, index --check and drifted on every pull request")
        )
    if available:
        print("\nnot wired yet:")
        print("\n".join(columns(available)))

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
