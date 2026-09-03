#!/usr/bin/env python3
"""PostToolUse hook: validate a note the moment it is written, not at review time.

CI is a round trip away and the verify stage of a docs run comes after every note is written.
Running the validator on one file as it lands turns a convention error into immediate feedback
while the note is still the thing being worked on.

Deliberately non-blocking. It reports and does not veto: a note can be legitimately incomplete
mid-edit -- an anchor path the same change is about to create, a spec whose code is not yet
written -- and a hook that refused those would be fighting the work rather than checking it.

Silent when the file is not a note (`check --skip-non-notes` decides that, so this file never has
to know where the docs root is), when nothing is wrong, and on any internal failure.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _engine

# The validator's line prefixes are a contract with this hook (doc_marshal.check ERROR_PREFIX and
# WARN_PREFIX). Selecting on them here rather than importing keeps the hook independent of
# which installed engine it resolved, and of that engine's Python.
PREFIXES = ("ERROR: ", "warn:  ")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    raw = (payload.get("tool_input") or {}).get("file_path")
    if not raw or not str(raw).endswith(".md"):
        return 0
    path = Path(raw)
    if not path.is_absolute():
        path = _engine.PROJECT / path
    if not path.is_file():
        return 0

    result = _engine.run("check", "--skip-non-notes", str(path))
    if result is None:
        return 0
    findings = [line for line in result.stdout.splitlines() if line.startswith(PREFIXES)]
    if not findings:
        return 0

    try:
        rel = path.resolve().relative_to(_engine.PROJECT)
    except ValueError:
        rel = path
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": (
                    f"doc-marshal check on {rel} (the docs convention validator, run automatically on "
                    "every note you write):\n"
                    + "\n".join(findings)
                    + "\n\nERROR lines fail CI and must be fixed before this run reports done. "
                    "Fix them in this note only -- do not edit notes outside the change. "
                    "`doc-marshal info --conventions` explains each rule."
                ),
            }
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
