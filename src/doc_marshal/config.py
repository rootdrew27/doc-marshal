"""The registry a docs root is validated against.

One hardcoded ontology, `standard`, and the marker file is location rather than configuration
(SPEC.md section 14). The loader of section 4 -- `extends`, per-type shallow merge,
`enabled = false`, `[rules]` -- lands in a later release and replaces the body of `load_registry`
without changing its signature. Until then a marker that carries keys is refused rather than ignored: a
configuration that validated as nothing would be exactly the silent failure this tool exists to
remove.
"""

from __future__ import annotations

import argparse
import tomllib
from pathlib import Path

from . import __version__
from .ontology import STANDARD, Registry
from .paths import DocMarshalError, find_docs_root
from .settings import SETTINGS, Settings


def load_registry(docs_root: Path, settings: Settings = SETTINGS) -> Registry:
    marker = docs_root / settings.marker_name
    if marker.is_file():
        try:
            data = tomllib.loads(marker.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise DocMarshalError(f"{marker}: not valid TOML -- {exc}") from exc
        if data:
            raise DocMarshalError(
                f"{marker} holds configuration ({', '.join(sorted(data))}), which doc-marshal "
                f"{__version__} does not read -- configuration arrives in a later release. Until "
                "then the file marks the docs root by existing, holds no keys, and any key fails "
                "every command."
            )
    return STANDARD


DOCS_ROOT_HELP = "docs root (default: the directory holding the marker)"


def add_docs_root_option(parser: argparse.ArgumentParser) -> None:
    """The `--docs-root` option every command takes, spelled once."""
    parser.add_argument("--docs-root", help=DOCS_ROOT_HELP)


def resolve(explicit: str | None, settings: Settings = SETTINGS) -> tuple[Path, Registry]:
    """The docs root and the registry in force for it -- the two things every command starts from."""
    docs_root = find_docs_root(explicit, settings)
    return docs_root, load_registry(docs_root, settings)
