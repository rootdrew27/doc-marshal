#!/usr/bin/env python3
"""SessionStart hook: give the session the docs index preview, the shared vocabulary and the types.

Deliberately thin. *What* a session is told is the engine's decision (`doc-marshal session-context`);
this file only resolves an engine, runs that command, and speaks the hook's JSON. Silent when the
project has no docs root and on any internal failure: a broken hook must not inject noise into
every session. The one thing it says on its own is that the project has a docs root but no engine
to validate it with, since silence there would look like a clean tree.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _engine


def emit(context: str) -> None:
    json.dump(
        {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}},
        sys.stdout,
    )


def main() -> int:
    prefix = _engine.command()
    if prefix is None:
        if _engine.has_docs_root():
            emit(_engine.MISSING_ENGINE)
        return 0
    result = _engine.run("session-context", "--quiet-if-absent", prefix=prefix)
    if result is None or result.returncode != 0:
        return 0
    context = result.stdout.strip()
    if context:
        emit(context)
    return 0


if __name__ == "__main__":
    sys.exit(main())
