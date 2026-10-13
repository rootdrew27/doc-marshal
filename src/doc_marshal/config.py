"""The effective profile a docs tree is validated against: a shipped profile, adjusted by the config.

The config is a folder at the top of the docs tree:

    .doc-marshal/
      config.toml         # extends, [anchors.*]; its existence marks the docs tree
      types/
        runbook.toml      # names a type the extended profile ships: merged over it
        plan.toml         # names no shipped type: a new one

A type file's name is the type's name. Merge is per type and shallow, and a nested table such as
`[structure]` merges the same way, so one key replaces one property and nothing reverts to a
default -- see docs/configuration.md. Whatever results goes through `from_dict`, so a user's type is
held to every combination `Profile` refuses in a shipped one.

Not read yet: `[policies]` and `exclude`. A key the loader does not read is refused, never
ignored: a configuration that validated as nothing would be exactly the silent failure this tool
exists to remove.
"""

from __future__ import annotations

import argparse
import tomllib
from pathlib import Path
from typing import Any

from .discovery import find_docs_tree, find_repo_root, moved_config
from .errors import DocMarshalError
from .ontology import PROFILES, Profile, from_dict, to_dict
from .paths import rel_to
from .settings import SETTINGS, Settings

# What `config.toml` may hold, and where each key that belongs elsewhere goes instead.
CONFIG_KEYS = frozenset({"extends", "anchors"})
NOT_HERE = {
    "types": "each type is its own file, {types}/<name>.toml, holding that type's table without a header",
    "policies": "the [policies] table is not read yet",
    "exclude": "`exclude` is not read yet",
}
# The properties a type no shipped profile declares must set, so a misspelt file name -- a
# `types/runbok.toml` holding `enabled = false` -- is an error rather than a new, empty type.
NEW_TYPE_REQUIRES = ("serves",)


def load_profile(docs_tree: Path, settings: Settings = SETTINGS) -> Profile:
    """The effective profile for this docs tree. The shipped `standard`, unchanged, when the tree
    has no config folder -- a tree named by `--docs-tree` need not carry one."""
    config = docs_tree / settings.config_name
    legacy = docs_tree / settings.legacy_config_name
    if legacy.is_file():
        raise DocMarshalError(moved_config(docs_tree, find_repo_root(docs_tree), settings))
    data = _read(config) if config.is_file() else {}
    where = rel_to(config, docs_tree.parent).as_posix()

    unknown = sorted(set(data) - CONFIG_KEYS)
    if unknown:
        types = rel_to(settings.types_dir(docs_tree), docs_tree.parent).as_posix()
        reasons = [f"`{key}`: {NOT_HERE[key].format(types=types)}" for key in unknown if key in NOT_HERE]
        raise DocMarshalError(
            f"{where}: key(s) this version does not read: {', '.join(unknown)}. "
            f"It reads {', '.join(sorted(CONFIG_KEYS))}." + "".join(f"\n  {r}" for r in reasons)
        )

    base_name, base = _extends(data.get("extends", "standard"), where, settings)
    merged = to_dict(base) if base is not None else {"anchors": {}, "types": {}}
    anchors = data.get("anchors", {})
    if not isinstance(anchors, dict) or not all(isinstance(t, dict) for t in anchors.values()):
        raise DocMarshalError(f"{where}: `anchors` is one table per field, [anchors.<field>]")
    for name, table in anchors.items():
        merged["anchors"][name] = _merge(merged["anchors"].get(name, {}), table)

    type_files = _type_files(docs_tree, settings)
    for name, path in type_files.items():
        table = _read(path)
        shipped = merged["types"].get(name)
        if shipped is None:
            missing = [key for key in NEW_TYPE_REQUIRES if key not in table]
            if missing:
                raise DocMarshalError(
                    f"{rel_to(path, docs_tree.parent).as_posix()}: names no type the {base_name} profile "
                    f"ships ({', '.join(merged['types']) or 'none'}), so it declares a new one, and a new "
                    f"type must set {', '.join(missing)}. Check the file name if it meant to adjust a "
                    "shipped type."
                )
        merged["types"][name] = _merge(shipped or {}, table)

    if not anchors and not type_files and base is not None:
        return base
    label = f"{base_name}, as configured" if base is not None else "configured"
    try:
        return from_dict(merged, label, settings)
    except (ValueError, TypeError) as exc:
        raise DocMarshalError(f"{rel_to(config.parent, docs_tree.parent).as_posix()}/: {exc}") from exc


def _read(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise DocMarshalError(f"{path}: not valid TOML -- {exc}") from exc


def _extends(value: object, where: str, settings: Settings) -> tuple[str, Profile | None]:
    """The profile `extends` names, or None for `extends = []`, which starts from nothing."""
    if value == []:
        return "empty", None
    if isinstance(value, str) and value in PROFILES:
        return value, PROFILES[value](settings)
    raise DocMarshalError(
        f"{where}: extends = {value!r} names no shipped profile. It takes one of "
        f"{', '.join(repr(p) for p in PROFILES)}, or [] to start from nothing."
    )


def _type_files(docs_tree: Path, settings: Settings) -> dict[str, Path]:
    """Every type file, keyed by the type it names. Anything else in the folder is an error: a
    file the loader passed over would be configuration that validated as nothing."""
    folder = settings.types_dir(docs_tree)
    if not folder.is_dir():
        return {}
    found: dict[str, Path] = {}
    for path in sorted(folder.iterdir()):
        if path.name.startswith("."):  # .DS_Store and kin: the filesystem's, not the user's
            continue
        label = rel_to(path, docs_tree.parent).as_posix()
        if not path.is_file() or path.suffix != ".toml":
            raise DocMarshalError(f"{label}: the types folder holds only <type>.toml files")
        if not settings.name_re.match(path.stem):
            raise DocMarshalError(f"{label}: a type's name is its file's, and must match {settings.filename_pattern}")
        found[path.stem] = path
    return found


def _merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    """`over` laid on `base`, one key at a time; a table present in both is merged the same way,
    one level down, so `[structure] max_rows = 30` replaces one number and keeps the rest."""
    out = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            out[key] = {**base[key], **value}
        else:
            out[key] = value
    return out


DOCS_TREE_HELP = "docs tree (default: the directory holding the config)"


def add_docs_tree_option(parser: argparse.ArgumentParser) -> None:
    """The `--docs-tree` option every command takes, spelled once."""
    parser.add_argument("--docs-tree", help=DOCS_TREE_HELP)


def resolve(explicit: str | None, settings: Settings = SETTINGS) -> tuple[Path, Profile]:
    """The docs tree and the effective profile for it -- the two things every command starts from."""
    docs_tree = find_docs_tree(explicit, settings)
    return docs_tree, load_profile(docs_tree, settings)
