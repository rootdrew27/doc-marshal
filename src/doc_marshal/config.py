"""The effective profile a docs tree is validated against.

One hardcoded ontology, `standard`, and the config file is location rather than configuration.
The loader of docs/configuration.md -- `extends`, per-type shallow merge,
`enabled = false`, `[policies]` -- lands in a later release and replaces the body of `load_profile`
without changing its signature. Until then a config that carries keys is refused rather than ignored: a
configuration that validated as nothing would be exactly the silent failure this tool exists to
remove.
"""

from __future__ import annotations

import argparse
import tomllib
from pathlib import Path

from . import __version__
from .discovery import find_docs_tree
from .errors import DocMarshalError
from .ontology import STANDARD, Profile
from .settings import SETTINGS, Settings


def load_profile(docs_tree: Path, settings: Settings = SETTINGS) -> Profile:
    config = docs_tree / settings.config_name
    if config.is_file():
        try:
            data = tomllib.loads(config.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise DocMarshalError(f"{config}: not valid TOML -- {exc}") from exc
        if data:
            raise DocMarshalError(
                f"{config} holds configuration ({', '.join(sorted(data))}), which doc-marshal "
                f"{__version__} does not read -- configuration arrives in a later release. Until "
                "then the file marks the docs tree by existing, holds no keys, and any key fails "
                "every command."
            )
    return STANDARD


DOCS_TREE_HELP = "docs tree (default: the directory holding the config)"


def add_docs_tree_option(parser: argparse.ArgumentParser) -> None:
    """The `--docs-tree` option every command takes, spelled once."""
    parser.add_argument("--docs-tree", help=DOCS_TREE_HELP)


def resolve(explicit: str | None, settings: Settings = SETTINGS) -> tuple[Path, Profile]:
    """The docs tree and the effective profile for it -- the two things every command starts from."""
    docs_tree = find_docs_tree(explicit, settings)
    return docs_tree, load_profile(docs_tree, settings)
