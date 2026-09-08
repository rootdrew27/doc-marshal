---
type: reference
updated: 2026-09-07
summary: Every doc-marshal verb, its flags, its exit status and what it is for, and how each one locates the docs tree
code_refs:
  - src/doc_marshal/cli.py
---

# The CLI surface

One command, `doc-marshal`, dispatching to one module per verb (`COMMANDS` in
`src/doc_marshal/cli.py`). Every reference to this tool -- in hooks, CI steps, agent-memory files
and the doctrine itself -- names a verb rather than an installation path.

`doc-marshal` with no arguments, `-h`, `--help` or `help` prints the verb list. `--version`, `-V`
or `version` prints the version. An unknown verb exits 2.

## Verbs

| Verb | Arguments and flags | What it is for |
| --- | --- | --- |
| `check` | `[paths...]`, `--all`, `--range A..B`, `--skip-non-notes`, `--format text\|github` | validate the named notes, or sweep the tree. `--range` names the change the freshness and lead policies read; without it they read the working tree against `HEAD`, which in a fresh CI checkout is empty, so CI must pass it. `--skip-non-notes` silently ignores paths that are not notes and exits 0 with no docs tree at all, for a hook handed every file a change touched. `--format github` emits one workflow command per finding |
| `index` | `--check` | regenerate `INDEX.md`. `--check` reports staleness and writes nothing |
| `drifted` | `--range A..B` or `--paths ...`, `--format text\|github`, `--print-range`, `--fail-on-match` | the notes whose path anchors name something a change touched. `--print-range` resolves the trunk and prints `<merge-base>..HEAD`, and nothing on the trunk itself |
| `new` | `<type> <path>`, `--summary` (required), `--title`, `--code-ref`, `--source`, `--status` | scaffold a note with the frontmatter and sections its type requires. It does not validate: the scaffold fails `check` until it is written |
| `info` | `[type]`, `--policies`, `--types`, `--marshalling`, `--format markdown\|json`, `--dump-toml` | the effective profile and the doctrine. Bare: the live types, one line each, with their anchors. `--dump-toml` prints the profile the way the configuration file of a later release spells it |
| `init` | `[path]`, `--claude-code`, `--pre-commit`, `--ci`, `--pin X.Y.Z` | mark a directory as the docs tree and write the integration files |
| `doctor` | -- | every route to the engine and every version the repository names, and whether they agree |
| `upgrade` | `<version>`, `--pins`, `--dry-run` | install a version and point every pin at it |
| `briefing` | `--quiet-if-absent` | what a fresh session is given about the docs tree |

One anchor flag per declared anchor field, singular and repeatable: `new` builds them from the
profile, so `code_refs` is `--code-ref` and `source` is `--source`.

## Exit statuses

| Status | Meaning |
| --- | --- |
| 0 | nothing to report. Warnings never change this, and neither does a `drifted` match without `--fail-on-match` |
| 1 | `check` found an error; `index --check` found a stale or unbuildable index; `doctor` found a problem; `drifted --fail-on-match` matched |
| 2 | a usage error, or anything the engine refuses: no docs tree, two configs, a config carrying keys, a malformed `--range`, an unknown verb |

## Locating the docs tree

Every verb but `init` and `upgrade` takes `--docs-tree PATH`. Resolution is `--docs-tree`, then
the `DOC_MARSHAL_DOCS_TREE` environment variable, then the directory holding `.doc-marshal.toml`
-- never a directory name. Inside a git repository the search is `git ls-files`, which honours
`.gitignore`; the working directory's ancestors are checked first, so a command run from inside
the tree finds its config without searching.

Two configs in one repository is an error naming both, because one repository has one docs tree.
No config at all is an error naming `init` and the directories it considered. `init` takes the
target as a positional path instead, defaulting to `docs/`, and `upgrade` works on the repository
rather than the tree.
