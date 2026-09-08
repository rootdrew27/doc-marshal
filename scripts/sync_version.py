"""Keep every copy of the version in step with `doc_marshal.__version__`.

`__version__` is the one source: `pyproject.toml` reads it through hatch, so the wheel can never
report a different version from the code. Elsewhere the version is copied by hand -- the plugin
manifest, the README's install commands, the pre-commit hook file's comment -- and this script
rewrites those from the source, or refuses a build when they disagree. Same pattern as
`render_doctrine.py`: derived, checked, never maintained by hand.

The README's two integration snippets go further than a version copy: they are generated whole,
from the same `integrate` functions `doc-marshal init --pre-commit --ci` writes files with. They
are the same text for two audiences -- a repository that has a pre-commit config and a workflow,
and one that does not -- so a reader who pastes one gets the block the engine would have written,
and a flag added on one side cannot fail to appear on the other. Marked `<!-- generated: ... -->`
in the README so the next person to edit them sees it.

    python scripts/sync_version.py            # rewrite the copies from __version__
    python scripts/sync_version.py --check    # exit 1 naming any copy that differs
    python scripts/sync_version.py --set 0.4.0  # bump __version__, then rewrite the copies
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from pathlib import Path

from doc_marshal.integrate import precommit_block, render_steps

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "src" / "doc_marshal" / "__init__.py"
SOURCE_RE = re.compile(r'^__version__ = "(\d+\.\d+\.\d+)"$', re.MULTILINE)
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")

# Each copy: the file, and the pattern whose one group is the version as that file spells it.
# `rev:` lines and `==X.Y.*` pins may appear more than once in a file; every occurrence is a copy.
COPIES: tuple[tuple[Path, re.Pattern[str], str], ...] = (
    (ROOT / "plugin" / ".claude-plugin" / "plugin.json", re.compile(r'("version": ")(\d+\.\d+\.\d+)(")'), "{v}"),
    (ROOT / "README.md", re.compile(r"(doc-marshal==)(\d+\.\d+\.\d+)()"), "{v}"),
    (ROOT / ".pre-commit-hooks.yaml", re.compile(r"(rev: v)(\d+\.\d+\.\d+)()"), "{v}"),
)


# Each generated block: the comment that names it in the README, and what the engine writes there.
# The `rev:` and the `==X.Y.*` pins inside them need no `COPIES` entry -- they arrive with the block.
README = ROOT / "README.md"
BLOCKS: tuple[tuple[str, Callable[[str], str]], ...] = (
    ("pre-commit", lambda version: precommit_block(version, indent="")),
    ("ci", lambda version: render_steps(version, indent="")),
)
BLOCK = "(<!-- generated: {name} -->\n```yaml\n)(.*?)(```\n)"


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


def render_blocks(version: str, check: bool) -> list[str]:
    """Rewrite the README's generated snippets from `integrate`, or with `check` report the ones
    that differ. Each block is re-found in the current text, so an earlier rewrite cannot shift a
    later block's offsets out from under it."""
    text = README.read_text(encoding="utf-8")
    stale: list[str] = []
    for name, render in BLOCKS:
        match = re.search(BLOCK.format(name=name), text, re.S)
        if match is None:
            stale.append(f"README.md: no `<!-- generated: {name} -->` block to write into")
            continue
        wanted = render(version)
        if match.group(2) == wanted:
            continue
        stale.append(f"README.md: the {name} snippet is not what `doc-marshal init` writes")
        text = text[: match.start(2)] + wanted + text[match.end(2) :]
    if stale and not check:
        README.write_text(text, encoding="utf-8")
        print(f"wrote {README.relative_to(ROOT)}")
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
    stale = sync(version, check) + render_blocks(version, check)
    if check and stale:
        print(
            f"derived copies disagree with the source (__version__ = {version}):\n  "
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
