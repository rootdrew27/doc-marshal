"""The constants of Tier 3, behind one object.

The filename pattern, the summary cap, the index and assets names, the forbidden names and the
excluded directories are not configurable until configuration lands (SPEC.md section 13). They
are routed through this one object anyway, so that exposing them under `[rules]` then is a schema
addition rather than a refactor through six modules: every consumer already takes a `Settings`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Suffixes that mean "markdown" to a writer. Only the first is a note; the rest are named errors,
# because a file the tool silently ignores is a note nobody validates.
NOTE_SUFFIX = ".md"
MARKDOWN_SUFFIXES = frozenset({".md", ".markdown"})


@dataclass(frozen=True)
class Settings:
    marker_name: str = ".doc-marshal.toml"
    """The file that marks the docs root and, in a later release, holds its configuration."""

    default_docs_dir: str = "docs"
    """Where `init` puts the docs root when not told otherwise."""

    env_var: str = "DOC_MARSHAL_DOCS_ROOT"
    """Overrides marker discovery; `--docs-root` overrides both."""

    index_name: str = "INDEX.md"
    """The one generated index. Upper-case so it does not read as a note and sorts to the top."""

    assets_dirname: str = "assets"
    """The one optional attachment directory, at the docs root. Exempt from everything, at any depth."""

    memory_names: frozenset[str] = frozenset({"CLAUDE.md", "AGENTS.md"})
    """Agent-memory files: never notes, anywhere under the docs root."""

    excluded_dirs: frozenset[str] = frozenset({".claude", ".git", ".github", ".obsidian"})
    """Tooling and metadata directories: nothing under them is a note."""

    filename_pattern: str = r"^[a-z0-9]+(-[a-z0-9]+)*$"
    """Notes and the folders holding them: kebab-case."""

    summary_max: int = 200
    """`summary` is one line -- the only prose the generated index shows."""

    future_slack_days: int = 1
    """An `updated` date this far ahead of today is tolerated -- a writer ahead of CI's UTC clock."""

    @property
    def forbidden_names(self) -> dict[str, str]:
        """Not allowed anywhere under the docs root, in any spelling of case, each with the reason
        reported to its author. Keyed by the lower-cased name."""
        return {
            "readme.md": f"the generated {self.index_name} is the docs root's only front door",
            # Any index but the generated one at the root. Caught by name rather than left to be
            # validated as a note, because "missing frontmatter" would not say what to do about it.
            self.index_name.lower(): f"the generated index is {self.index_name}, spelled so, at the docs root only",
        }

    def forbidden_reason(self, path: Path) -> str | None:
        """Why a markdown file may not exist under the docs root, or None when its name is allowed.
        The one reading of the rule: `classify` calls it to decide, the validator to explain."""
        if path.suffix != NOTE_SUFFIX:
            return f"notes are {NOTE_SUFFIX} files -- rename it"
        return self.forbidden_names.get(path.name.lower())

    @property
    def name_re(self) -> re.Pattern[str]:
        return re.compile(self.filename_pattern)

    @property
    def numbered_name_re(self) -> re.Pattern[str]:
        """The whole filename of a numbered note: `NNNN-` and then the ordinary pattern."""
        return re.compile(NUMBER_PREFIX + self.filename_pattern.lstrip("^"))


# The number a numbered note carries, written once. `NUMBER_PREFIX_RE` is the looser question the
# scaffolder asks when choosing the next free number: a badly named `0007-Bad Name.md` still
# occupies 0007, and handing that number out again would stack a collision on a naming error.
NUMBER_PREFIX = r"^(\d{4})-"
NUMBER_PREFIX_RE = re.compile(NUMBER_PREFIX)
# What separates that number from the title in the note's H1: `0007 -- Parking`. Written by `new`
# and demanded by `check`, so it is spelled once.
NUMBER_TITLE_SEPARATOR = " -- "

SETTINGS = Settings()
