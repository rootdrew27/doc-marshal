"""The registry a docs root is validated against.

0.1 ships one hardcoded ontology, `standard`, and the marker file is location rather than
configuration (SPEC.md section 14). The loader of section 4 -- `extends`, per-type shallow merge,
`enabled = false`, `[rules]` -- lands in 0.2 and replaces the body of `load_registry` without
changing its signature. Until then a marker that carries keys is refused rather than ignored: a
configuration that validated as nothing would be exactly the silent failure this tool exists to
remove.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from . import __version__
from .ontology import STANDARD, Registry
from .paths import DocMarshalError
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
                f"{__version__} does not read -- configuration arrives in 0.2. In this release the "
                "file marks the docs root by existing, and must be empty."
            )
    return STANDARD
