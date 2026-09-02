"""Command dispatch for `doc-marshal`.

One entry point rather than a directory of scripts, because every reference to this tool -- in
hooks, CI steps, agent-memory files and the convention's own prose -- names a verb instead of an
installation path. See SPEC.md section 6 for the surface this will grow.
"""

from __future__ import annotations

import sys

from . import __version__


def main() -> int:
    if "--version" in sys.argv[1:]:
        print(f"doc-marshal {__version__}")
        return 0
    print(
        f"doc-marshal {__version__} -- name reserved, not yet implemented.\n"
        "The design is in SPEC.md: https://github.com/rootdrew27/doc-marshal",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
