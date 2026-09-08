"""`doc-marshal upgrade`: move every facet that names a version to the same new one.

    doc-marshal upgrade 0.4.0          # install it, then move the pre-commit rev and the CI pin
    doc-marshal upgrade 0.4.0 --dry-run
    doc-marshal upgrade 0.4.0 --pins   # the second half alone, after an install

The verb drives the install rather than reconciling pins after one, because the two orders are not
equally safe. Bumping the `rev:` first leaves pre-commit running a version the project has not
installed; installing first and stopping leaves the agent validating against a version CI does not
run. Either way the repository sits, for as long as the user takes to run the second command, in a
state its own `doctor` fails. Doing both here closes that window, and names the verb after work it
actually does.

It runs in two phases because the process that starts an upgrade is the *old* engine. Phase one
installs and hands off to the newly installed executable; phase two -- `--pins` -- is that
executable rewriting the facets it can now name correctly. The handoff is a subprocess rather than
`os.execv`: the exit status has to reach a shell the same way on every platform. When no engine
reporting the new version can be found afterwards, it stops instead of writing the pins from the
old one -- an upgrade that visibly stopped half done beats one that reports success in the old
version's words.

Only `uv` is driven (see `manager`). Anything else is handed its two steps and stops.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from . import __version__, check, doctor
from .discovery import cwd_repo
from .errors import DocMarshalError
from .integrate import PYPROJECT, normalize, pins, set_pins
from .manager import detect

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+\S*$")

# Said out loud on every upgrade, because both are ways to end up worse off while believing the
# upgrade worked.
AFTERWARDS = """
Two things about upgrading this tool:

  `pre-commit autoupdate` moves the doc-marshal `rev:` on its own, and nothing else. That is the
  one facet moving without the environment or the CI pin, which is exactly the disagreement
  `doc-marshal doctor` reports. `doc-marshal upgrade <version>` is the route that moves all of them.

  A minor release may enforce checks the old one did not, so a tree that passed yesterday can fail
  today. That is why `check --all` runs as part of an upgrade rather than surprising you after it.
"""


def upgraded_engine(repo_root: Path, version: str) -> Path | None:
    """The executable that reports `version` after an install: the one that has to write the pins.

    Asked as "which engine is the new one" rather than "what path did the install land at", and
    answered through `doctor`'s own resolution so that the routes searched here are the routes
    `doctor` reports. Both are checked because a project may install into its virtualenv or onto
    PATH; a stale engine at either is not an answer, which is what comparing the version rules out.
    """
    for found in (doctor.in_venv(repo_root), doctor.on_path()):
        if found and found[1] and normalize(found[1]) == version:
            return Path(found[0])
    return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="doc-marshal upgrade",
        description="Install a version and point every facet that names one at it.",
    )
    parser.add_argument("version", help="the version to move to, as X.Y.Z")
    parser.add_argument("--pins", action="store_true", help="rewrite the pins only, without installing")
    parser.add_argument("--dry-run", action="store_true", help="say what would change and write nothing")
    args = parser.parse_args(argv)

    version = normalize(args.version)
    if not VERSION_RE.match(version):
        raise DocMarshalError(f"not an X.Y.Z version: {args.version!r}")
    _, repo_root, _ = cwd_repo()

    if not args.pins:
        manager = detect(repo_root)
        steps = manager.steps(version)
        if args.dry_run:
            print(f"would install with {manager.name}:")
            for step in steps:
                print(f"  {step}")
            print(f"would then rewrite every pin in {repo_root} to {version}, and run doctor and check --all")
            return 0
        if not (manager.drives and manager.available):
            reason = (
                f"{manager.name} is not on PATH" if manager.drives else f"this release drives uv, not {manager.name}"
            )
            print(f"This project uses {manager.name} and {reason}. Run:\n")
            for step in steps:
                print(f"  {step}")
            print(
                f"\nthen finish the upgrade -- the pins, doctor and check --all:\n\n  doc-marshal upgrade {version} --pins"
            )
            return 0
        code = manager.install(version)
        if code != 0:
            raise DocMarshalError(f"{manager.name} could not install doc-marshal=={version} (exit {code})")
        # Everything below has to be decided by the version that was just installed: the pins it
        # writes, the checks it enforces, and the version `doctor` compares against are all its own.
        engine = upgraded_engine(repo_root, version)
        if engine is None:
            raise DocMarshalError(
                f"{manager.name} installed doc-marshal=={version}, but no engine reporting "
                f"{version} is resolvable here -- not in the project's virtualenv, not on PATH. "
                f"The pins are left alone rather than written by {__version__}, which would name a "
                f"version this process cannot run. Finish with the new engine:\n\n"
                f"  doc-marshal upgrade {version} --pins"
            )
        return subprocess.run([str(engine), "upgrade", version, "--pins"], cwd=str(repo_root), check=False).returncode

    if args.dry_run:
        print(f"would rewrite every pin in {repo_root} to {version}")
        return 0

    if normalize(__version__) != version:
        print(
            f"warn:  writing pins for {version} while running {__version__}. Run `doc-marshal "
            "doctor` once the install lands.",
            file=sys.stderr,
        )
    changed = set_pins(repo_root, version)
    if changed:
        print("wrote:")
        for line in changed:
            print(f"  {line}")
    elif any(pin.where != PYPROJECT for pin in pins(repo_root)):
        # Nothing changed because every rev and CI pin already names this version: the case a
        # second run of `upgrade` lands in, which is not the case of having nothing to write.
        print(f"every pre-commit rev and CI pin already names {version} -- nothing to move")
    else:
        print("no pre-commit rev or CI pin to move -- `doc-marshal init --pre-commit --ci` writes both")

    print()
    status = doctor.main([])
    print()
    try:
        status = max(status, check.main(["--all"]))
    except DocMarshalError as exc:
        print(f"check --all did not run: {exc}", file=sys.stderr)
    print(AFTERWARDS)
    if status:
        print(f"doc-marshal is now {version} and every pin names it. The reports above are what to fix next.")
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
