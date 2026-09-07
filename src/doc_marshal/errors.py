"""The one exception the CLI turns into a message and an exit status."""

from __future__ import annotations


class DocMarshalError(Exception):
    """A failure the CLI reports as a message and an exit status, without a traceback."""
