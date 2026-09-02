"""Command dispatch for `doc-marshal`.

One entry point rather than a directory of scripts, because every reference to this tool -- in
hooks, CI steps, agent-memory files and the convention's own prose -- names a verb instead of an
installation path. Each verb is a module with a `main(argv) -> int`; this file only routes.
"""

from __future__ import annotations

import importlib
import sys

from . import __version__
from .paths import DocMarshalError

COMMANDS: dict[str, tuple[str, str]] = {
    "check": ("check", "validate the named notes, or --all to sweep the tree"),
    "index": ("index", "regenerate INDEX.md; --check reports staleness without writing"),
    "affected": ("affected", "notes whose repo-path anchors name code a change touched"),
    "new": ("new", "scaffold a note the validator will accept"),
    "info": ("info", "the effective registry; info <type>, --conventions, --process"),
    "init": ("init", "mark a directory as the docs root and write the integration files"),
    "doctor": ("doctor", "report the resolved engine version and flag a plugin/repo mismatch"),
    "session-context": ("session", "what a fresh session is given about the docs tree"),
}

USAGE = "usage: doc-marshal <command> [options]\n       doc-marshal --version\n"


def usage() -> str:
    width = max(len(name) for name in COMMANDS)
    lines = [USAGE, "commands:"]
    for name, (_, help_text) in COMMANDS.items():
        lines.append(f"  {name.ljust(width)}  {help_text}")
    lines.append("\n`doc-marshal <command> --help` for each command's options.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args or args[0] in ("-h", "--help", "help"):
        print(usage())
        return 0
    if args[0] in ("--version", "-V", "version"):
        print(f"doc-marshal {__version__}")
        return 0
    command = args[0]
    if command not in COMMANDS:
        print(f"doc-marshal: unknown command {command!r}\n\n{usage()}", file=sys.stderr)
        return 2
    module = importlib.import_module(f".{COMMANDS[command][0]}", __package__)
    try:
        return int(module.main(args[1:]))
    except DocMarshalError as exc:
        print(f"doc-marshal {command}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
