"""Which project manager installs into this repository, behind one object a run asks.

`Manager` is the port: it answers the one question `upgrade` puts to a project manager -- how this
project installs a named version of doc-marshal -- and, where the manager can be driven, does it.
`detect` builds one for the repository it runs in. There is deliberately no `Protocol`, for the
reason `git.py` gives: with the interesting behaviour in one subclass the class itself is the
interface, and a second manager is an addition rather than a rewrite.

Only `uv` is driven. Every other manager is detected and handed the steps to run, because
installing on someone's behalf through a manager whose lockfile and environment layout we have not
tested is the kind of help that leaves a project worse than it found it. `steps` is not a fallback
for a missing case: it is the honest answer for a manager this release does not drive.

Standard library only, and no network: the manager itself resolves and downloads.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class Manager:
    """A project manager, named and able to say how it installs a version."""

    name = "pip"
    drives = False

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root

    @property
    def available(self) -> bool:
        """Whether the manager itself is on PATH. A repository can name a manager the machine
        running this does not have."""
        return shutil.which(self.name) is not None

    def steps(self, version: str) -> list[str]:
        """The commands that install `version` into this project, for a user to run."""
        return [f"pip install doc-marshal=={version}   # in the project's virtualenv"]

    def install(self, version: str) -> int:
        """Run the install, streaming the manager's own output. Only for `drives` managers."""
        raise NotImplementedError(f"{self.name} is detected but not driven")


class Uv(Manager):
    name = "uv"
    drives = True

    def steps(self, version: str) -> list[str]:
        return [f"uv add --dev doc-marshal=={version}"]

    def install(self, version: str) -> int:
        # One command writes both facets it owns: the dependency table and the environment. The
        # exact pin is the point -- `uv add doc-marshal` alone writes a range, and a range is the
        # disagreement `doctor` exists to catch (SPEC.md section 19).
        argv = ["uv", "add", "--dev", f"doc-marshal=={version}"]
        print(f"$ {' '.join(argv)}")
        return subprocess.run(argv, cwd=str(self.repo_root), check=False).returncode


class Poetry(Manager):
    name = "poetry"

    def steps(self, version: str) -> list[str]:
        return [f"poetry add --group dev doc-marshal=={version}"]


def detect(repo_root: Path) -> Manager:
    """The manager this repository uses. Lockfile first, then the pyproject table, then pip.

    A lockfile is the stronger signal: it exists only because the manager ran here, while a
    `[tool.*]` table can outlive the manager that wrote it.
    """
    if (repo_root / "uv.lock").is_file():
        return Uv(repo_root)
    if (repo_root / "poetry.lock").is_file():
        return Poetry(repo_root)
    pyproject = repo_root / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8") if pyproject.is_file() else ""
    if "[tool.uv" in text:
        return Uv(repo_root)
    if "[tool.poetry" in text:
        return Poetry(repo_root)
    return Manager(repo_root)
