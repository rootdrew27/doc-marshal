#!/usr/bin/env python3
"""SessionStart hook: give the session the docs index preview, the shared vocabulary and the types.

Deliberately thin. *What* a session is told is the engine's decision (`doc-marshal briefing`);
this file only resolves an engine, runs that command, and speaks the hook's JSON. Silent when the
project has no docs tree and on any internal failure: a broken hook must not brief every session
with noise. It speaks for itself twice, both times because silence would look like a clean tree:
the project has a docs tree but no engine to validate it with, or a config that does not load.
The second is told to the user as well as the session, the way Claude Code reports a broken
settings file: which file, and what is wrong with it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _engine


def emit(context: str, user_message: str | None = None) -> None:
    out: dict[str, object] = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}
    if user_message:
        out["systemMessage"] = user_message
    json.dump(out, sys.stdout)


def main() -> int:
    prefix = _engine.command()
    if prefix is None:
        if _engine.has_docs_tree():
            emit(_engine.MISSING_ENGINE)
        return 0
    result = _engine.run("briefing", "--quiet-if-absent", prefix=prefix)
    problem = _engine.config_problem(result)
    if problem:
        emit(
            "doc-marshal: the docs tree's config does not load, so every doc-marshal command exits 2 "
            f"and no note is validated until it is fixed:\n{problem}\nThis is context, not a task. "
            "The config folder is the user's: if the work touches the docs, say that the config "
            "needs fixing, and edit it only if they ask -- each edit there needs their approval.",
            f"doc-marshal: config error -- notes are not validated until it is fixed.\n{problem}",
        )
        return 0
    if result is None or result.returncode != 0:
        return 0
    context = result.stdout.strip()
    if context:
        emit(context)
    return 0


if __name__ == "__main__":
    sys.exit(main())
