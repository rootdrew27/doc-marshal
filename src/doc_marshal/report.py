"""How findings are collected and printed.

One `Report` per run, shared by `check`, `new` and the vocabulary builder, so a finding reads the
same wherever it was raised: level, path relative to the repository root, message. The two
spellings of a line -- the hook's prefix and the GitHub workflow command -- live here too, so
`affected` and `check` cannot drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .paths import rel_to

# How a finding is printed. The plugin's PostToolUse hook selects on these, so they are a contract
# rather than incidental formatting.
PREFIXES = {"warning": "warn:  ", "error": "ERROR: "}

Finding = tuple[str, Path, str]  # (level, path relative to the repo root, message)


def workflow_command(level: str, path: Path, msg: str) -> str:
    """One GitHub Actions workflow command, so a pull request shows the message on the file it
    names. `%` and newlines are what the syntax reserves."""
    return f"::{level} file={path.as_posix()}::{msg.replace('%', '%25').replace(chr(10), '%0A')}"


@dataclass
class Report:
    """Findings, each carrying the note's path relative to `root` -- the repository root, so a
    line reads the same in CI, in a pre-commit hook and in the plugin's hook output, whatever the
    working directory and however the target was spelled."""

    root: Path
    findings: list[Finding] = field(default_factory=list)

    def error(self, path: Path, msg: str) -> None:
        self.findings.append(("error", rel_to(path, self.root), msg))

    def warn(self, path: Path, msg: str) -> None:
        self.findings.append(("warning", rel_to(path, self.root), msg))

    def count(self, level: str) -> int:
        return sum(1 for found, _, _ in self.findings if found == level)

    def lines(self) -> list[str]:
        """Warnings first, then errors, each prefixed for the hook to select on."""
        return [
            f"{PREFIXES[level]}{path}: {msg}"
            for wanted in ("warning", "error")
            for level, path, msg in self.findings
            if level == wanted
        ]

    def annotations(self) -> list[str]:
        """The findings as GitHub Actions workflow commands, so a pull request shows each one on
        the file it names."""
        return [workflow_command(level, path, msg) for level, path, msg in self.findings]
