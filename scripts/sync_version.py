"""Keep every copy of the version in step with `doc_marshal.__version__`.

`__version__` is the one source: `pyproject.toml` reads it through hatch, so the wheel can never
report a different version from the code. Three files carry a copy nothing derives -- the plugin
manifest, the README's pre-commit and CI snippets, and the pre-commit hook file's comment -- and
this script rewrites them from the source, or refuses a build when they disagree. Same pattern as
`render_prose.py`: derived, checked, never maintained by hand.

    python scripts/sync_version.py            # rewrite the copies from __version__
    python scripts/sync_version.py --check    # exit 1 naming any copy that differs
    python scripts/sync_version.py --set 0.4.0  # bump __version__, then rewrite the copies
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "src" / "doc_marshal" / "__init__.py"
SOURCE_RE = re.compile(r'^__version__ = "(\d+\.\d+\.\d+)"$', re.MULTILINE)
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")

# Each copy: the file, and the pattern whose one group is the version as that file spells it.
# `rev:` lines and `==X.Y.*` pins may appear more than once in a file; every occurrence is a copy.
COPIES: tuple[tuple[Path, re.Pattern[str], str], ...] = (
    (ROOT / "plugin" / ".claude-plugin" / "plugin.json", re.compile(r'("version": ")(\d+\.\d+\.\d+)(")'), "{v}"),
    (ROOT / "README.md", re.compile(r"(rev: v)(\d+\.\d+\.\d+)()"), "{v}"),
    (ROOT / "README.md", re.compile(r"(doc-marshal==)(\d+\.\d+)(\.\*)"), "{minor}"),
    (ROOT / ".pre-commit-hooks.yaml", re.compile(r"(rev: v)(\d+\.\d+\.\d+)()"), "{v}"),
)


def source_version() -> str:
    match = SOURCE_RE.search(SOURCE.read_text(encoding="utf-8"))
    if match is None:
        sys.exit(f'{SOURCE.relative_to(ROOT)}: no `__version__ = "X.Y.Z"` line')
    return match.group(1)


def set_source(version: str) -> None:
    text, count = SOURCE_RE.subn(f'__version__ = "{version}"', SOURCE.read_text(encoding="utf-8"))
    if count != 1:
        sys.exit(f"{SOURCE.relative_to(ROOT)}: expected one `__version__` line, found {count}")
    SOURCE.write_text(text, encoding="utf-8")


def sync(version: str, check: bool) -> list[str]:
    """Rewrite each copy, or with `check` report the ones that differ. Returns the stale copies."""
    minor = ".".join(version.split(".")[:2])
    stale: list[str] = []
    for path, pattern, form in COPIES:
        wanted = form.format(v=version, minor=minor)
        text = path.read_text(encoding="utf-8")
        found = {m.group(2) for m in pattern.finditer(text)}
        if not found:
            stale.append(f"{path.relative_to(ROOT)}: no version found for {pattern.pattern!r}")
            continue
        if found == {wanted}:
            continue
        stale.append(f"{path.relative_to(ROOT)}: {', '.join(sorted(found))} (source says {wanted})")
        if not check:
            path.write_text(pattern.sub(rf"\g<1>{wanted}\g<3>", text), encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT)}")
    return stale


def main(argv: list[str]) -> int:
    check = "--check" in argv
    if "--set" in argv:
        if check:
            sys.exit("--set and --check are two different jobs")
        try:
            version = argv[argv.index("--set") + 1]
        except IndexError:
            sys.exit("--set needs a version, e.g. --set 0.4.0")
        if not VERSION_RE.match(version):
            sys.exit(f"not an X.Y.Z version: {version!r}")
        set_source(version)
        print(f"wrote {SOURCE.relative_to(ROOT)}")
    version = source_version()
    stale = sync(version, check)
    if check and stale:
        print(
            f"version copies disagree with __version__ = {version}:\n  "
            + "\n  ".join(stale)
            + "\n-- run scripts/sync_version.py",
            file=sys.stderr,
        )
        return 1
    if not stale:
        print(f"every copy says {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
