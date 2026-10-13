"""The exceptions the CLI turns into a message and an exit status."""

from __future__ import annotations

# The stderr line a config that does not load is reported on, by every command. The plugin's hooks
# select on it to tell the user and the session which file is broken and how.
CONFIG_PREFIX = "CONFIG: "


class DocMarshalError(Exception):
    """A failure the CLI reports as a message and an exit status, without a traceback."""


class ConfigError(DocMarshalError):
    """A config that does not load: the file at fault, from the repository root, and what is wrong
    with it. The CLI prints it on a `CONFIG: ` line, which the plugin's hooks select on."""

    def __init__(self, path: str, detail: str) -> None:
        super().__init__(f"{path}: {detail}")
        self.path = path
        self.detail = detail
