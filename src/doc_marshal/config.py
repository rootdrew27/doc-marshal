"""The effective profile a docs tree is validated against: the one its config folder declares.

The config is a folder at the top of the docs tree, and it is the whole profile:

    .doc-marshal/
      config.toml         # [anchors.*], the anchor fields; its existence marks the docs tree
      types/
        reference.toml    # one file per type: the file is the type
        runbook.toml

A type exists only if its file does, and its file's name is its name. A file is the entire type --
nothing is inherited, so any property can be removed by deleting its key -- and an anchor field
exists only if `config.toml` declares it. `init` writes the standard profile's anchor fields and
types as the starting point; from then on the tree's own files are what it is held to, and
`doctor` says where they differ from the profile `init` wrote. Everything goes through
`from_dict`, so a user's type is held to every combination `Profile` refuses in a shipped one.

Not read yet: `[policies]` and `exclude`. A key the loader does not read is refused, never
ignored: a configuration that validated as nothing would be exactly the silent failure this tool
exists to remove.
"""

from __future__ import annotations

import argparse
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .discovery import find_docs_tree, find_repo_root
from .errors import ConfigError
from .ontology import Profile, TypeProblem, from_dict, standard
from .paths import rel_to
from .settings import SETTINGS, Settings

# What `config.toml` may hold, and why each key that does not belong there is refused.
CONFIG_KEYS = frozenset({"anchors"})
NOT_HERE = {
    "types": "each type is its own file, {types}/<name>.toml, holding that type's table without a header",
    "extends": "the config folder is the whole profile: a type exists only if its file in {types}/ does",
    "policies": "the [policies] table is not read yet",
    "exclude": "`exclude` is not read yet",
}
# What every type file must set, so a file holding a stray key or two is an error rather than a
# type with nothing to say about the reader it serves.
TYPE_REQUIRES = ("serves",)


def load_profile(docs_tree: Path, settings: Settings = SETTINGS) -> Profile:
    """The effective profile for this docs tree: the anchor fields `config.toml` declares and one
    type per file in `types/`. Named `standard` while it equals the shipped profile. A tree with no
    config at all -- one named by `--docs-tree` -- is held to the shipped `standard`."""
    config = docs_tree / settings.config_name
    if not config.is_file():
        return standard(settings)
    data = _read(config, docs_tree)

    unknown = sorted(set(data) - CONFIG_KEYS)
    if unknown:
        folder = rel_to(settings.types_dir(docs_tree), find_repo_root(docs_tree)).as_posix()
        reasons = [f"`{key}`: {NOT_HERE[key].format(types=folder)}" for key in unknown if key in NOT_HERE]
        raise _fail(
            config,
            docs_tree,
            f"key(s) this version does not read: {', '.join(unknown)}. "
            f"It reads {', '.join(sorted(CONFIG_KEYS))}." + "".join(f"\n  {r}" for r in reasons),
        )
    anchors = data.get("anchors", {})
    if not isinstance(anchors, dict) or not all(isinstance(t, dict) for t in anchors.values()):
        raise _fail(config, docs_tree, "`anchors` is one table per field, [anchors.<field>]")

    type_files = _type_files(docs_tree, settings)
    types: dict[str, Any] = {}
    for name, path in type_files.items():
        types[name] = _read(path, docs_tree)
        missing = [key for key in TYPE_REQUIRES if key not in types[name]]
        if missing:
            raise _fail(path, docs_tree, f"a type must set {', '.join(missing)}")

    try:
        profile = from_dict({"anchors": anchors, "types": types}, "configured", settings)
    except TypeProblem as exc:
        raise _fail(type_files[exc.type_name], docs_tree, exc.detail) from None
    except ValueError as exc:  # an anchor field: those are declared in config.toml
        raise _fail(config, docs_tree, str(exc)) from None
    shipped = standard(settings)
    if (profile.anchor_fields, profile.types) == (shipped.anchor_fields, shipped.types):
        return Profile(shipped.name, profile.anchor_fields, profile.types, settings)
    return profile


def differences(profile: Profile, settings: Settings = SETTINGS) -> dict[str, list[str]]:
    """Where a tree's profile departs from the shipped `standard` that `init` wrote: the types
    whose file differs, the types standard does not have, the standard types with no file, and the
    same three for anchor fields. Empty lists where it agrees. What `doctor` reports -- a newer
    engine's change to a shipped type reaches a tree only by its file being edited, so this is
    where a user sees what they hold apart from it."""
    shipped = standard(settings)
    pairs: tuple[tuple[str, Mapping[str, object], Mapping[str, object]], ...] = (
        ("types", profile.types, shipped.types),
        ("anchor fields", profile.anchor_fields, shipped.anchor_fields),
    )
    out: dict[str, list[str]] = {}
    for label, ours, theirs in pairs:
        out[f"{label} edited"] = [n for n in ours if n in theirs and ours[n] != theirs[n]]
        out[f"{label} added"] = [n for n in ours if n not in theirs]
        out[f"{label} removed"] = [n for n in theirs if n not in ours]
    return out


def _read(path: Path, docs_tree: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise _fail(path, docs_tree, f"not valid TOML -- {exc}") from None


def _fail(path: Path, docs_tree: Path, detail: str) -> ConfigError:
    """The error for a config file, named as the user would open it: from the repository root.
    Built only on failure, so a clean load never pays for the repository lookup."""
    return ConfigError(rel_to(path, find_repo_root(docs_tree)).as_posix(), detail)


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
        if not path.is_file() or path.suffix != ".toml":
            raise _fail(path, docs_tree, "the types folder holds only <type>.toml files")
        if not settings.name_re.match(path.stem):
            raise _fail(path, docs_tree, f"a type's name is its file's, and must match {settings.filename_pattern}")
        found[path.stem] = path
    return found


DOCS_TREE_HELP = "docs tree (default: the directory holding the config)"


def add_docs_tree_option(parser: argparse.ArgumentParser) -> None:
    """The `--docs-tree` option every command takes, spelled once."""
    parser.add_argument("--docs-tree", help=DOCS_TREE_HELP)


def resolve(explicit: str | None, settings: Settings = SETTINGS) -> tuple[Path, Profile]:
    """The docs tree and the effective profile for it -- the two things every command starts from."""
    docs_tree = find_docs_tree(explicit, settings)
    return docs_tree, load_profile(docs_tree, settings)
