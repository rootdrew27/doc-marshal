# doc-marshal -- design spec

**Status:** agreed, unbuilt. Written 2026-09-02 from a design session held in the repository the
prototype was developed in.

**Provenance:** the tooling this project extracts was a working prototype that lived as a skill kit
in a private application repository. Every rule below has been exercised against a real 30-note
documentation tree. This document records what the extraction decided, including the parts that
reverse the prototype.

This is a *spec* in the sense the ontology uses the word: it describes work before it is built,
and its Validation section carries items that are not yet closed. It is not a reference. When
the code exists and disagrees with this file, the code is right and this file is stale.

---

## 1. What this is

A documentation system for repositories whose primary reader is a coding agent.

It has three parts:

1. **An engine** -- a validator, index builder and drift detector for a tree of typed markdown
   notes. Every rule it enforces is read off a registry rather than hardcoded per check.
2. **A preset** -- `standard`, a five-type ontology with an opinionated argument for why each
   type exists and how to route between them.
3. **Integrations** -- a Claude Code plugin, a pre-commit hook, and a CLI that CI calls directly.

**The tool is `doc-marshal`** -- the package, the CLI, the module (`doc_marshal`) and the
repository. **The directory it governs is whatever the project already calls its documentation**,
defaulting to `docs/` and identified by a `.doc-marshal.toml` marker inside it rather than by its
name (section 4.1.1).

The distinguishing idea is the **anchor**: every living note declares, in frontmatter, what
outside itself would falsify it. That makes "which docs did this diff invalidate?" a question
with a mechanical answer, which is the difference between documentation that rots silently and
documentation that reports its own staleness.

## 2. Positioning -- engine, not convention

The product is the engine. The five-type ontology ships as a preset and is a convenience.

This was decided deliberately against the alternative, which was to sell the convention itself
(the way Conventional Commits or Keep a Changelog are sold) and treat the validator as the thing
that makes it stick. Engine-as-product buys users the freedom to bring their own ontology and be
held to it just as strictly. The cost, accepted: the shipped ontology is one option among many
rather than the point, and the engine competes on capability with general docs linters.

The consequence that does the most work downstream: **anchoring must be an engine capability, not
a fact about two hardcoded field names.** See §3.3.

## 3. The ontology

### 3.1 The standard preset

Five types. A type names the reader it serves, and nothing else; the anchor minimum follows from
what outside the note would falsify it (see §3.3).

| Type | Serves | Anchor minimum |
| --- | --- | --- |
| `reference` | someone looking up a fact -- decided by this repo, or observed from outside it | any of `code_refs`, `source` |
| `runbook` | someone running a procedure | `code_refs` |
| `decision` | someone about to reopen a settled choice | none |
| `spec` | someone reading, building or validating a feature's behaviour as a whole | `code_refs` once `done` |
| `nomenclature` | someone choosing what to call a thing | none |

**Revised 2026-09-03.** The 0.1 preset had eight types, and three of them encoded an axis rather
than a reader. Whether a fact was decided here or observed from outside is a property of the fact,
so `reference` now accepts either anchor and requires at least one; `background`, which differed
from `reference` only on that axis, is gone. Whether the thing described exists yet is a lifecycle,
so `spec` carries the shared `status` (`proposed`, `in-progress`, `done`) and is anchored only
from `done`; the rule that a finished spec is converted to an `explanation` is gone with the
`explanation` type, since a done spec *is* the description of the built feature, and rationale
lives in the `decision` that chose or the `reference` that states the fact. `history` is gone too:
a dead end with a choice behind it is a `decision`, and the rest is `git log`. The one real
deployment showed the skew the axes caused -- fifteen decisions to one reference in a tree of
thirty-two -- and a type system with fewer, reader-named types is one an agent routes on reliably.

Two types require no anchor. `decision` is append-only and anchored by its own content. `nomenclature`
is falsified by the words the repo uses, not by a path.

Anchor minimums are **any-of**: `requires` lists the fields of which a note must carry at least
one, and `requires_from` names the status from which that binds. A `done` spec edited by a change
that touched none of its anchored code is a warning, since the doc may now lead the code and the
status would no longer be true. A spec is living at every status: rewritten in place when the code
changes, and set back to `in-progress` when it is rewritten ahead of the code.

The `## Related` section the 0.1 conventions required at the end of every note is gone with the
same revision. Inline links on first mention carry connectivity and the resolver still checks
them; a required trailing list of neighbours restated those links with a reason clause, and the
reason was the only thing it added.

### 3.2 What a type declares

A type is data. Every facet below is enforced by the validator and applied by the scaffolder, and
no check hardcodes a type name.

| Facet | Meaning |
| --- | --- |
| `serves`, `voice`, `mutability` | prose, rendered by `info` |
| `requires`, `requires_from` | anchor fields of which a note must carry at least one, and the status from which that binds |
| `statuses`, `default_status` | allowed `status` values, empty means the type has none; the shared lifecycle is a registry constant a type may name |
| `folder` | the one folder under the docs root this type lives in |
| `numbered` | filename carries a unique `NNNN-` prefix |
| `fixed_name` | the one filename this type may take, exempt from the naming pattern |
| `root_required` | one instance must exist at the docs root |
| `additive` | a nested instance may not redefine a key an ancestor defines |
| `append_only` | never edited after acceptance, so its wording cannot be corrected |
| `supersession` | field names and status recording that this note was replaced |
| `skeleton` | what the scaffolder writes |
| `required_sections` | the `##` sections a prose note carries: each once, in this relative order, each with content; other sections anywhere |
| `empty_at` | (section, status) pairs: in that status the section, if present, must be blank |
| `structure` | the body shape other checks parse -- see below |

**`required_sections`** is the shape rule for prose. Every note has exactly one H1, first, and a
numbered note's H1 carries its number; a type with required sections must have each present,
once, in order, and written once HTML comments are stripped. The registry refuses a type whose
skeleton does not write its required sections in that order, so `new` and `check` read one list.
In the preset: `decision` requires Context, Decision, Alternatives considered, Consequences;
`spec` requires Overview, Behavior, Validation and is `empty_at` Open questions once `done`;
`runbook` requires Prerequisites, Steps; `reference` requires nothing. *(0.3.)*

**`structure`** exists for a type whose body is *data* rather than prose. It declares the exact
`##` sections in order, the table's columns, which column is the key, which columns other notes
are scanned against, and caps on rows, cell length and total file size. A type with a `structure`
is validated for shape as an error rather than a warning, because a renamed column does not
degrade the checks built on it -- it silently turns them off, and a check that has quietly stopped
running is worse than one that never existed.

`nomenclature` is the only preset type with a `structure` today. Its `Avoid` column is read by every
other note's vocabulary check.

### 3.3 Anchors

Anchor **fields** are declarable, not fixed. Each declares what it holds and how its entries
resolve.

| `resolves` | Meaning | On the drift spine |
| --- | --- | --- |
| `repo-path` | a path from the repo root, must exist | yes |
| `docs-path` | a path that must resolve inside the docs root | no |
| `url` | an `http`/`https` URL, validated for shape | no |
| `opaque` | validated for presence only | no |

The preset declares two: `code_refs` (`repo-path`) and `source` (`docs-path` or `url`).

**The drift spine** is the set of anchor fields with `resolves = "repo-path"` -- what the lead
check reads when it asks whether a `done` spec's code moved. `doc-marshal affected` matches every
path-valued field, spine and `docs-path` alike, against a git diff, so a note whose source note or
attachment changed is reported too *(0.3; before, only the spine)*. Any path anchor must be
tracked by git, whichever field holds it. This generalises the prototype, where
`affected_docs.py` read the literal string `code_refs` and `check_source` hardcoded the rule that
`source` must resolve inside the docs root. Both were convention judgments about two specific
fields baked into engine code; they become instances of a general rule.

**The engine does not require any ontology to have a `repo-path` anchor.** A user may declare
every field `opaque` and float free of the spine. Decided deliberately: freedom belongs to the
user, and an ontology with no drift detection is a choice they are entitled to make loudly in one
config file.

Anchor requirements per type are **minimums, not permitted sets**. Any declared field is legal on
any type and is validated whenever present.

## 4. Configuration

Everything in this section is designed now and **built in 0.2**. See §14.

### 4.1 The marker file

**`.doc-marshal.toml`, inside the docs root.** It does two jobs: it marks which directory is the
docs root, and it holds the configuration. An empty file is valid TOML, so 0.1 writes it empty and
0.2 fills it -- nothing is renamed between releases.

TOML is read with `tomllib`, standard library from 3.11, which is the floor this package sets.

### 4.1.1 The docs root is marked, not guessed

The prototype hunts upward for a directory literally named `agent-docs`, which is safe only because
that name is unusual. The default directory is now `docs/` -- the name every repository already
uses -- and `docs/` is occupied in a large share of them by a published site: Sphinx (`conf.py`),
MkDocs, Docusaurus, Jekyll, mdBook. Discovery by name would walk into one and report several
hundred errors on files that were never notes.

A marker fixes this at the right level: **discovery does not depend on the directory's name at
all.** The docs root is the directory containing `.doc-marshal.toml`. A project that prefers
`notes/` or `agent-docs/` puts the marker there and nothing else changes, and a repository can hold
a Sphinx `docs/` *and* a marshal tree elsewhere without ambiguity -- the case a name-based default
could not express.

Rules:

- **Exactly one marker per repository.** Two is an error naming both, since one repo has one docs
  root.
- **The marker is not a note.** It is classified alongside the generated index and the agent-memory
  files -- never validated, never indexed.
- **Precedence for location:** `--docs-root`, then `$DOC_MARSHAL_DOCS_ROOT`, then the marker. There
  is no name-based fallback and no guessing.
- **`doc-marshal init` creates it**, defaulting to `docs/` and taking a path argument for anything
  else. With no marker, every other command fails with a message naming `init` and listing the
  directories it considered.
- `init` **warns** when the target looks like a published site -- it holds `conf.py`, `mkdocs.yml`,
  `_config.yml`, `docusaurus.config.*` or `book.toml` -- or when it holds markdown without
  frontmatter. A warning rather than a refusal, because adopting the convention on an existing tree
  is a legitimate thing to do and the marker makes the intent explicit.

This supersedes the earlier design in which configuration lived in a repo-root `doc-marshal.toml`
with a `[tool.doc-marshal]` fallback in `pyproject.toml`. One location beats three, and a `docs_root`
config key is no longer needed -- it existed only to compensate for name-based discovery.

### 4.2 Composition

```toml
extends = "standard"   # the default when omitted; `extends = []` starts from nothing
```

Presets are named and shipped in the package. More may be added later (`minimal`) without a new
config mechanism -- that is the same `extends` key with more data behind it.

Rejected: merge-by-default, which makes the preset's types unremovable furniture; and
replace-by-default, which makes adding one type mean retyping every skeleton.

### 4.3 Merge semantics

**Per-type shallow merge over the extended preset.** Writing `[types.reference] serves = "..."`
yields the preset's `reference` with one field replaced -- not a fresh type whose other facets
revert to defaults. The alternative would mean that adding a `folder` to `decision` silently
strips its numbering, supersession and skeleton.

**Merge is shallow per table, and nested tables merge the same way.** `[types.nomenclature.structure]
max_rows = 30` overrides one number without restating `columns`, `sections` or the other caps.

### 4.4 Disabling

Disabling is a **value in the type's own table**, not a parallel list:

```toml
[types.runbook]
enabled = false
```

This follows the eslint (`"off"`), stylelint (`null`) and pyright (`"none"`) model rather than
ruff's `select`/`ignore` lists. The research behind the choice: ruff needs lists because it has
thousands of prefix-namespaced rule codes, and it has since **deprecated `extend-ignore`** because
the replace-versus-extend distinction collapsed in practice. Doc types are a small named entity
space, where a keyed map is already the natural structure.

Concretely, `enabled = false` beats a `disable = [...]` list on four counts: one place to look for
whether a type is live; a typo'd `[types.histry]` is a validatable unknown-type error where
`disable = ["histry"]` is silently a no-op; re-enabling downstream in an `extends` chain is
`enabled = true` rather than list subtraction; and it needs no new mechanism, being one more facet
under the merge rule that already exists.

### 4.5 Weakening a built-in

Permitted. `[types.reference] code_refs = false` is legal.

"Always enforced" is a property of the **engine**, not of the preset: there is no severity
configuration, no warn-only mode, and no inline suppression. Whatever registry results is enforced
completely. Freezing the preset's internals would defend a much weaker thing while making the
the preset's types furniture nobody can move.

### 4.6 The rules table

```toml
[rules]
em_dash = false
filename_pattern = "^[a-z0-9-]+$"
summary_max = 300
forbidden_names = []
exclude = ["docs/legacy/**"]
```

Rule-level configuration exists, expressed as **values**, with disabling as a legal value -- the
same shape as §4.4, so there is one idea to learn rather than two.

`exclude` is the incremental-adoption mechanism: it quarantines *files* visibly rather than
weakening a *rule* everywhere. Partial adoption already half-works, because `check` accepts a file
list and pre-commit passes only staged files; `exclude` extends that to `--all` in CI.

### 4.7 What is not configurable, ever

**No inline suppression.** No `<!-- doc-marshal-disable -->` in a note, no per-line ignores. This
is the line, and it is the only prohibition the design defends absolutely. A hundred scattered
suppressions are unauditable; everything in a config file shows up in review and can be printed
back as the effective ruleset by `doc-marshal info`.

**Tier 1 invariants**, regardless of configuration: frontmatter parses; `type` names a live type;
declared anchors are present and resolve according to their kind; links resolve, including heading
anchors; a type's declared facets hold; the index is generated rather than written.

## 5. Prose lives in the package

The convention's prose -- the rules, the argument for each type, the routing guidance -- ships
**inside the package** and is obtained by calling the CLI. It is never copied into a user's
repository.

This dissolves rather than solves several problems at once: no emitted copy means no staleness
check, no ownership boundary between the tool's file and the user's edits, and no question about
whether a rules file inside the docs root is itself a note that must pass validation.
Output is filtered to *enabled* types, so it is more accurate than any stored file, and it always
matches the installed version.

It also deletes an enforcement point. The prototype's `build_types.py` exists solely to keep
stored tables in agreement with the registry, and is checked in CI and in the commit hook.
Rendering on demand makes that entire staleness class impossible.

**Markdown is primary**, with `--format json` available for third parties building on the engine.

Two consequences:

- **User-declared types supply their own prose.** `serves`/`voice`/`mutability` inline; a
  `description_file` key for anything longer, because multi-paragraph markdown inside a TOML
  string is miserable to author and to diff.
- **Humans need it on the web.** A reviewer on a pull request cannot run the CLI, and the
  conventions are the sales pitch. The canonical human rendering lives in the repository README
  and the project's docs site. `init` writes one small pointer file into the target repo -- a
  pointer, not a copy, so it cannot drift.

**Revised 2026-09-03.** This repository keeps one rendering of the standard preset in `rendered/`:
the rules, the type arguments and the process, generated by `scripts/render_prose.py` from
the same source `info` renders, regenerated by a pre-commit hook and committed back by CI on every
push to main. It is derived, never edited, and lives only here -- a user's repository still holds
no copy. That is the difference between it and the staleness class rendering-on-demand removed:
the copy cannot disagree with the source at the same commit, and a machine rather than a person
keeps it current.

## 6. CLI surface

One command, `doc-marshal`, replacing the prototype's five script paths. That single name is what
makes the prose portable: reference files, hooks, CI steps and agent-memory files stop naming
installation paths.

| Command | Purpose |
| --- | --- |
| `check [paths...]` / `check --all` | validate the named notes, or sweep the tree; `--range` names the change for the freshness and lead checks; `--format github` annotates a pull request |
| `index` | regenerate `INDEX.md`; `--check` reports staleness without writing |
| `affected` | notes whose `repo-path` anchors name code a change touched; `--range`, `--paths`, `--format github` |
| `new <type> <path>` | scaffold a note with its type's frontmatter and required sections; it does not validate, and the scaffold fails `check` until written |
| `info` | the compact effective registry -- enabled types, one line each, with anchors |
| `info <type>` | one type in full: argument, skeleton, facets, statuses |
| `info --rules` | every rule `check` enforces that is not per-type; the boundaries of those checks are §18 |
| `info --process` | the update-docs process, staged |
| `info --types` | every enabled type in full, the preset's types document |
| `info --format json` / `info --dump-toml` | the effective registry as data, and as the configuration schema |
| `init [path] [--claude-code]` | mark a directory as the docs root and write the integration files; defaults to `docs/` |
| `doctor` | report the resolved engine version and flag a plugin/repo mismatch |
| `session-context` | what a fresh session is given -- see §7 |

`build_types` has no successor: its rendering moves inside `info`.

## 7. Session injection

A `SessionStart` hook injects three blocks:

1. **The index preview** -- folder names with note counts, and nothing else, ending with a pointer
   to `doc-marshal index` for the full list. **Uniform reduction at every size, including the top
   level.**
2. **The docs root's `NOMENCLATURE.md`, as content.** One line per term from the parsed table --
   the term, its definition, the aliases it rules out -- then the prose sections as written, with
   frontmatter and HTML comments stripped. The terms and the aliases they rule out are the content;
   a summary of a vocabulary is a second vocabulary. Only the root note is injected -- a nested one
   governs its subtree and is read on arriving there. *(Revised 2026-09-03: was verbatim.)*
3. **The compact `info` block** -- the enabled types and their anchors, one line per type.

The reasoning for (1): `INDEX.md` in the prototype is injected in full and uncapped. It measured
**7592 characters at 30 notes** and grows linearly with the tree forever, while the `nomenclature` type
capped *itself* at 6000 characters with the explicit argument that it "is emitted into every session"
(now 35 rows plus 3000 characters of prose, §16).
The argument that justifies the smaller cap applies with more force to the file that had none.

Rejected: capping by byte count, which makes the injected content depend on how verbose other
people's summaries are, so adding one long summary could silently truncate a different note out of
the index. Rejected: a note-count threshold with degradation, which introduces two renderings and
a cliff. Rejected: exempting top-level notes, which reintroduces the inconsistency that the
uniform rule removes.

The cost, accepted: a session that needs to route to a document spends one tool call. That is paid
only by sessions that touch documentation, where the previous design charged every session for a
full index including the majority that never open a doc.

## 8. Package layout

```
doc-marshal/
  pyproject.toml                   zero runtime deps; console_script: doc-marshal
  LICENSE                          MIT
  README.md                        the standard preset's prose -- the sales pitch
  SPEC.md                          this file
  src/doc_marshal/
    __main__.py                    python -m doc_marshal
    cli.py                         subcommand dispatch
    ontology.py                    DocType, Structure, Supersession; the standard preset
    settings.py                    the constants of Tier 3, behind one object (see §13)
    config.py                      TOML loader, merged over a preset          [0.2]
    paths.py                       docs-root discovery, path classification, frontmatter
    check.py index.py affected.py new.py info.py init.py doctor.py
    session.py                     what a fresh session is given
    prose/
      rules.md                     rendered by `info --rules`
      doc-types.md                 rendered by `info` and `info <type>`
      process.md                   rendered by `info --process`
  plugin/
    .claude-plugin/plugin.json
    skills/update-docs/SKILL.md    ~20 lines, deferring to `info --process`
    hooks/hooks.json               PostToolUse validation, SessionStart injection
  .pre-commit-hooks.yaml
  tests/
```

`DocType` is the **single internal representation**. The preset constructs it in Python -- keeping
the dataclass docstrings, type checking, and cross-references like `Structure(max_cell=SUMMARY_MAX)`
that TOML would flatten into a duplicated literal. The config loader is an alternate constructor
for the same objects.

**The round-trip test is the forcing function**: serialize the built-in registry to TOML, load it
back, assert equality. If the schema cannot express the shipped preset, the schema is too weak,
and that is discovered on day one rather than in a user's bug report. The same serializer backs
`info --dump-toml`, which is how a user sees a worked example without reading Python.

## 9. Dependency policy

Runtime dependencies are permitted, and must pass three tests:

1. **Pure Python.** No compiled extensions.
2. **It must not replace a strictness boundary.**
3. **It earns a decision record.**

**Nothing passes today.** The obvious candidate was replacing the hand-rolled frontmatter parser
with PyYAML, and it fails test 2: the prototype's `parse_frontmatter` deliberately reads a
*subset* -- scalars and dash lists -- and raises on anything richer, so a block the convention does
not sanction fails loudly rather than validating as empty. PyYAML accepts nested maps, flow style,
anchors, and the Norway problem where a bare `no` becomes `False`. The strictness is the
convention, enforced at parse time. The same argument rules out a real markdown parser: the table
and heading readers are strict subset readers, and `check_structure` depends on that.

`tomli-w` is taken as a **development dependency** for the round-trip test.

**Why pure-Python is load-bearing:** it keeps `python3 -m doc_marshal` working from a bare
checkout, and keeps the install a single pure wheel with no build step on any platform -- which is
what lets a pre-commit hook or a `uvx` call in CI resolve it in seconds. A single C extension
ends that.

## 10. The Claude Code plugin

**The plugin is an add-on to the package, not a distribution of it.** It carries no copy of the
engine. Its hooks resolve the project's own `doc-marshal` -- the project's virtualenv first, then
PATH -- so the agent validates against exactly the version the repository installed and CI runs.
With no engine installed the hooks do nothing, except that SessionStart says so once in a project
that has a docs root, since silence there would look like a clean tree. `doctor` reports what
each route resolves and flags a mismatch.

*Revised 2026-09-02.* An earlier draft vendored the engine into the plugin so that installing the
plugin was the entire installation. Dropped: it presented the plugin as the product when the
package is, and it introduced a second engine version, updated on plugin install and pinned by
nothing, that `doctor` then existed mostly to police. The audience lost is whoever wanted
zero-install Claude Code tooling and no CI or pre-commit check, which is not the audience the
drift detector is for.

**SKILL.md is thin** -- roughly twenty lines: a description good enough for skill matching, then
an instruction to run `doc-marshal info --process` and follow it. The prototype's 274 lines of
process prose move into the package, where they are versioned with the engine and shared with
every other agent.

**The plugin's real value is the two hooks**, which no other harness provides: PostToolUse
validation of each note as it is written, and SessionStart injection. The extra Bash round-trip
before the agent knows the process is the price of the process matching the installed engine.

## 11. Agent compatibility

Claude Code is the priority; the design stays vendor-neutral.

- `doc-marshal init` writes **`AGENTS.md`** by default -- the neutral surface, which Claude Code
  also reads.
- `doc-marshal init --claude-code` writes **`CLAUDE.md`** instead, and additionally writes the
  `.claude/settings.json` permission entries for `doc-marshal`, `uv run doc-marshal` and
  `.venv/bin/doc-marshal` so the agent is not prompted on every validator call. (The bare name
  alone was found not to match anything runnable in a non-interactive session, V5.)
- `--claude-code` also writes one import line, `@<docs root>/CLAUDE.md`, into the repository's
  root `CLAUDE.md`, creating the file if there is none. Claude Code loads a nested memory file only
  once a session reads under its directory, so without the line a session that never opens the
  docs never learns they exist. `doctor` reports a docs-root `CLAUDE.md` the root does not import.
  Other harnesses have no import syntax, so plain `init` prints the reference line for the root
  `AGENTS.md` and writes nothing there. *(Revised 2026-09-03.)*
- The flag generalises later to `--agent claude-code|codex|cursor`.
- **Supported: Claude Code on macOS and Linux.** That is what the hooks, the import line and the
  smoke test exercise. The CLI, pre-commit and CI paths run anywhere Python does; the hook engine
  lookup and `doctor` probe a Windows virtualenv's `Scripts/` as well as `bin/`, but nothing on
  Windows or in another harness is tested, and consumers are told so. *(2026-09-03.)*

Either way the file is descriptive: what the tree, its commands and its two special files are
for, and nothing about how to use them -- that is `doc-marshal info`, versioned with the engine.
A Codex or Cursor user gets the same process by the same route with no plugin at all. Non-Claude agents get no write-time
validation; pre-commit catches their errors, later.

## 12. Enforcement points

| When | What runs | Effect |
| --- | --- | --- |
| every `Write`/`Edit` to a note | `check <that file>` via the plugin's PostToolUse hook | reports into the session; never blocks |
| every `git commit` | `check` on staged notes, `index`, via the pre-commit framework | errors block; regenerated files fail the hook for re-adding |
| every pull request | `check --all`, `index --check` | errors fail the build; a stale index warns |
| every pull request | `affected --format github` | annotates anchored notes; never fails |

**The pre-commit framework replaces the prototype's 218-line native hook**, which regenerated
`INDEX.md` and staged it into the same commit. The framework will not stage; a hook that modifies
files fails and you re-add. Accepted, because that is exactly how `black`, `ruff-format` and
`prettier` behave, so a public user meets a failure mode they have seen a hundred times rather than
a bespoke one -- and silently adding files to someone's commit is the more surprising of the two
behaviours. The invariant that matters, that no *pushed* branch carries a stale index, is held by
CI regardless. `git config core.hooksPath` is retired: no contributor ever runs it.

Neither pull-request job takes a `paths:` filter. Half of what they check is whether anchors still
resolve, and those break in the change that renames or deletes the code -- which by definition
touches no documentation.

CI calls `uvx doc-marshal check --all` directly. **No composite GitHub Action in 0.1**: it is sugar
over a three-line step, and a repository with no users does not need a marketplace listing.

## 13. Stability contract

SemVer, plus pinning -- and pinning is free at every enforcement point: pre-commit by `rev:`, CI
by `uvx doc-marshal==0.5.*`.

**Minor releases may add checks.** The README says so plainly. A user who pinned does not see a
new check until they choose to bump, and upgrade-requires-fixes is a normal process when the
upgrade was a choice.

Rejected: a warnings-in-minors, errors-in-majors rollout ceremony. Pinning already solves the
problem it was designed for, and the ceremony would delay a genuinely important check by a major
release.

**The one real hazard** would be a second engine version the repository does not pin -- an agent
validating at 0.6 while CI runs 0.5. The plugin carries no engine of its own (§10), so the only
versions in play are the ones the repository installs and pins, and `doctor` compares those.

**Tier 3 constants** -- the filename pattern, `SUMMARY_MAX`, the index and assets directory names,
the forbidden names, the excluded directories -- are **not configurable until configuration
lands**. They are routed through one settings object anyway, so exposing them then is a schema
addition rather than a refactor through six modules.

## 14. Release plan

### 0.1 -- the extraction

No configuration. `init` writes an empty `.doc-marshal.toml` marker, which is location rather than
configuration. `standard` is the only ontology and it is hardcoded. Ships:

- the engine, registry-driven, with every check the prototype has
- the CLI of §6
- the thin plugin with both hooks, running the repository's own engine
- `.pre-commit-hooks.yaml`
- a README carrying the preset's prose
- MIT license, PyPI release

Fresh repository, **no history transfer**. A subtree split would capture only one of four source
directories -- the hooks, the commit hook and the workflows live elsewhere and are being dropped or
rewritten -- and the files that came across would be restructured into `src/`, giving renames on
top of a partial history. The reasoning stays readable in the prototype's history, and most of it
is in the docstrings regardless.

**Not dogfooded initially.** When it is, the split is: the package's prose documents the
convention, and the repository's own docs tree documents the implementation.

### Then -- run it against a real tree

The real integration test is an existing project's documentation tree, used informally during
development and never checked in here as a fixture. Such a tree needs zero configurability, and
running it exercises the things paper cannot check: whether the plugin resolving the repository's
own engine is comprehensible, whether `info`-instead-of-files works for an agent mid-task, and
whether a thin SKILL.md still gets matched and followed. A test suite in `tests/`, when it lands,
is built on synthetic trees so the repository stays self-contained; 0.2 ships without one, on the
smoke script alone, by the consumer's choice (decision 38).

### 0.2 -- the five-type preset

The revision of §3.1: five types, any-of anchor minimums with `requires_from`, the shared
lifecycle on `spec`, no `## Related` section. With it, the descriptive pointer and the root
`CLAUDE.md` import of §11, `check --format github`, and `rendered/` of §5. A breaking change to
what trees validate, so a minor bump rather than a patch; MakeRent migrates after the release.

Also in 0.2, from MakeRent's review of 0.1 (decisions 29-38): every shape rule an error, exact-spelling
path resolution, anchors strictly inside the repository, `new` reading paths from the current
directory, no em dash rule, the nomenclature note without its `Historical` column and under two
caps, the session receiving that note's content rather than its file, and the marker stating its
own blast radius.

### 0.3 -- the validator says what it means

Two reviews on 2026-09-03 fed this release. First, enforced structure per type (§3.2): the
`required_sections` and `empty_at` facets, the title rule on every note, populated sections, and
the four per-type spines. Second, the limits found migrating MakeRent to 0.2.0, under one theme --
no silent passes: path anchors tracked by git and spelled without dot segments; unknown
frontmatter keys, a `superseded_by` on an unreplaced note and a note naming itself as errors;
forbidden names in any case, a nested index and a misspelled `.md` suffix as errors; images and
angle-bracket links checked, code spans not, heading anchors exact; the alias scan reading the
summary, skipping comments and following a wrap; `--range` validated as `A..B` or exit 2; a pure
`git mv` not an edit; `affected` matching `docs-path` anchors and refusing absolute `--paths`;
`new` no longer validating and never writing a superseded note; `doctor` exiting 1 with no docs
root or no engine. Git is required. A breaking change to what trees validate, so a minor bump;
consumers pinned to `0.2.*` see none of it until they choose to.

### Later -- configuration

The loader of §4, gated by the round-trip test. Brings with it `[rules]`, `exclude`, Tier 3, and
the `[types.nomenclature.structure]` overrides for `max_rows` and `max_chars`. Not numbered: the
marker and the SPEC say "a later release" rather than promise a version that may carry something
else first.

## 15. Decision log

Each row is a decision taken in the design session, with the alternative it beat.

| # | Decision | Instead of |
| --- | --- | --- |
| 1 | The engine is the product; the ontology is a preset | selling the convention, with the validator as enforcement |
| 2 | Anchor fields are declarable, with a `resolves` kind | two hardcoded field names with hardcoded resolution asymmetry |
| 3 | `extends`, with the preset built in Python and TOML as an alternate constructor | shipping the preset as TOML for a forcing function -- a round-trip test buys that more cheaply |
| 4a | Per-type shallow merge, nested tables included | replace semantics, which silently strips unmentioned facets |
| 4b | `enabled = false` inside the type's table | a parallel `disable = [...]` list, per the ruff/eslint research |
| 4c | Weakening a built-in is permitted | freezing the preset, which makes its types immovable furniture |
| 5 | `[rules]` values with disabling as a value; `exclude` globs | no rule configuration at all -- the position collapsed, since `em_dash = false` is disabling a rule |
| 5b | **No inline suppression.** The one absolute prohibition | per-line ignores, which are unauditable at scale |
| 6 | Prose lives in the package, fetched by CLI | emitting it into the repo, with a staleness check and an ownership boundary |
| 7 | Markdown-primary output; compact `info` injected at SessionStart | JSON-primary, which would force arguments into fields |
| 8 | Dependency policy of three tests; nothing qualifies yet | zero-deps as dogma, or taking PyYAML because deps are allowed |
| 9 | `doc-marshal` for repo, package, module and CLI | `agent-docs` for everything -- PyPI rejects it as too similar to the existing `agentdocs` |
| 10 | Vendor-neutral `AGENTS.md`, `--claude-code` for `CLAUDE.md` plus permissions | Claude-only, abandoning most of the public audience |
| 11 | pre-commit framework | the native hook, whose auto-staging is not worth the per-clone install step |
| 12 | SemVer and pinning; minors may add checks | a warnings-then-errors rollout ceremony |
| 13 | 0.1 is the extraction; config is 0.2 | building the configurable engine first |
| 14 | Commit-then-extract, fresh repo | `git subtree split`, which captures one of four source directories |
| 15 | Index preview reduced to folder names and counts | full injection (uncapped), a byte cap, or a note-count threshold with degradation |
| 16 | Uniform reduction, top level included | exempting top-level notes, reintroducing two renderings |
| 17 | No dogfooding initially; MIT | dogfooding from `git init` |
| 18 | The docs root is any directory the project chooses, defaulting to `docs/` | a fixed `agent-docs/`, which after the rename was orphaned branding a project never chose |
| 19 | The root is found by a `.doc-marshal.toml` **marker inside it**, never by name | a name-based hunt, which with a `docs/` default walks into Sphinx and MkDocs trees; and a repo-root `docs_root` config key, which the marker makes unnecessary |
| 20 | The marker **is** the config file, empty in 0.1 | a bare sentinel plus a separate repo-root config, which is two files and a rename between releases |
| 21 | Five types; a type names its reader only, and authorship and lifecycle are properties of the note | eight types, three of which encoded an axis rather than a reader |
| 22 | Anchor minimums are any-of, with `requires_from` for a status threshold | all-of minimums, and a separate type per authorship |
| 23 | No `## Related` section; inline links carry connectivity | a required trailing link list with reason clauses |
| 24 | A `rendered/` copy in this repository, derived and committed by CI | the README carrying the prose by hand, or nothing readable without the CLI |
| 25 | `--claude-code` imports the docs-root pointer from the root `CLAUDE.md`, and `doctor` checks the line | relying on the nested memory file, which loads only once a session reads under the docs root |
| 26 | The pointer file is descriptive -- what exists and what it is for | a pointer that instructs, duplicating `info --process` in a file the engine cannot regenerate |
| 27 | The preset revision is 0.2; configuration moves to 0.3 | shipping a change that breaks existing trees under 0.1.x |
| 28 | The vocabulary type is `nomenclature`, at `NOMENCLATURE.md` | `context` / `CONTEXT.md`, which reads as general context storage and collides with the word everywhere else it is used |
| 29 | Every rule a script judges on shape alone is an error: freshness against the change's own window, misplaced attachments, a non-note named on the command line | warnings, which the consumer found read as optional |
| 30 | Freshness is held to the day the change began -- today for the working tree, the earliest author date of a `--range` | comparing against today, which failed every note dated the day it was edited once its pull request aged |
| 31 | Paths resolve by exact spelling against real directory listings, and an anchor names something strictly inside the repository | `Path.exists()`, which on APFS passes what Linux CI fails and which accepted `.` |
| 32 | `new` reads a path from the current directory | guessing between the repo root and the current directory, which placed notes silently |
| 33 | No em dash rule | a warning on the literal character and a ` -- ` convention |
| 34 | Nomenclature has no `Historical` column; a renamed term's old word goes in `Avoid` and the `decision` is the history | an unscanned column recording history in the one file every session pays for |
| 35 | Two nomenclature caps: rows for the table, 3000 characters for everything outside it | one whole-file cap, which 35 rows alone nearly filled |
| 36 | The session receives the nomenclature note's content -- one line per term, then its prose sections -- not its file | verbatim injection, frontmatter and comments included |
| 37 | The marker states its own blast radius; no configuration escape hatch before 0.3 | an empty file, and a refusal message naming the wrong release |
| 38 | Claude Code on macOS and Linux is the supported platform; Windows and other harnesses get the CLI and nothing tested beyond it. No test suite in 0.2 | claiming a neutrality the tests do not back; pytest on synthetic trees, deferred by the consumer |
| 39 | Prose structure is `required_sections`: present, once, in relative order, written; other sections anywhere. `structure` stays the exact-set rule for parsed bodies | the exact-set model everywhere, which forbids a section a decision genuinely needs; presence in any order, which loses the reading order |
| 40 | `decision` requires Context, Decision, Alternatives considered, Consequences; `spec` requires Overview, Behavior, Validation; `runbook` requires Prerequisites, Steps; `reference` requires nothing | a subset for decisions; a spine on references, which the prose does not support |
| 41 | Every note has one H1, first; a numbered note's H1 carries its number; a required section may not repeat | policing heading-level skips, which fires on legitimate documents |
| 42 | A required section must have content once HTML comments are stripped | presence only, under which a scaffold satisfies the rule the moment it is written |
| 43 | `spec` writes `## Open questions`, optional, and a `done` spec may hold nothing under it, expressed as `empty_at` data | a required-but-may-be-empty flag; enforcing Validation item shape or id stability across a range |
| 44 | Structural maintenance on an accepted decision -- a heading, a link, an `updated` bump -- is not an edit of the decision; append-only stays a convention | machine-enforcing append-only, or grandfathering old decisions by run scope |
| 45 | A path anchor of either kind must be tracked by git; outside a repository a path anchor is an error. Git is required | existence on disk, which passed for months in one checkout and failed in every other |
| 46 | `new` does not validate anchors or minimums; naming and placement only. The scaffold fails `check` until written, and `new`'s last line is the gate | two implementations of one rule, which wrote notes `check` rejected |
| 47 | A note is never born superseded; `superseded_by` implies the superseded status; neither supersession field names the note itself. No reciprocity check | accepting the state MakeRent's decisions 0008 and 0010 were silently in |
| 48 | A multi-word alias matches across whitespace within a paragraph, at most one line break; the scan reads `summary` and skips HTML comments | a single-line match, blind to every wrapped alias in a tree wrapped at 100 columns |
| 49 | `--range` is `A..B`, both commits, `A` an ancestor of `B`, or exit 2; `check` and `affected` alike | silent exit 0 on a bad range, which disabled the freshness and lead checks in CI unnoticed |
| 50 | Forbidden names match in any case; a nested `INDEX.md` is forbidden; `.markdown` and `.MD` are errors by name | ignoring them, which left notes nobody validated |
| 51 | Links: inline code spans skipped, images checked, `<dest>` accepted, heading anchors exact; `?query`, HTML `<a>` and reference-style definitions are documented boundaries | resolving fragments case-insensitively, which GitHub does not |
| 52 | Unknown frontmatter keys are errors; the known set is the registry's | passing them, under which a misspelled anchor field anchored nothing |
| 53 | No `.` or `..` segment in a frontmatter path | normalising them, so the text named one path and the resolver another |
| 54 | A pure `git mv` is not an edit for freshness; a plain `mv` is | demanding a bump on a note nothing in which became stale |
| 55 | `affected` matches every path field; absolute `--paths` exit 2 | matching the spine only, so a changed source note reported nothing |
| 56 | `doctor` exits 1 with no docs root or no engine | reporting "every copy agrees" about nothing |
| 57 | Nomenclature: duplicate terms and an alias equal to a term are errors, compared in any case; `\|` is a literal pipe; the prose cap counts the body only; an anchor is legal on the type | the text saying "carries none" while the validator accepted one |
| 58 | Configuration is "a later release", unnumbered; the session block steers to `new` in one sentence rather than listing sections per type | naming 0.4 and renaming again later; four lines per session that `new` makes unnecessary |
| 59 | The rules document states only what `check` enforces, each rule an error unless marked a warning. Writing guidance the tool cannot check lives in the process, and the argument for each type in its own document | a conventions document mixing enforced rules with advice, with the split recoverable only from two lists at its end |
| 60 | The boundaries of the parser and the checks are recorded in §18, not in the rules | boundary paragraphs inline in the rules, which read as rules and doubled the document's length |
| 61 | The document, its flag, its renderer and its rendered copy are `rules`; the agent-memory files are "instructions to an agent, outside the rules"; renaming an attachment is governed by the anchors that name it, not by a prohibition | `conventions`, which reads as suggestion; "not documentation", which the tool did not mean; "never rename anything under `assets/`", which the tool does not hold |
| 62 | The types document carries each type's registry facts, rendered from the same source as `info <type>`, and its prose is the unchecked argument for the type, said so once in the preamble | prose restating the registry per type, a second copy of every enforced fact that had already drifted on numbering and supersession |

## 16. Carried in from the prototype review

Findings from reviewing the prototype, to be handled during extraction.

- **`init` must scaffold `NOMENCLATURE.md`** as well as the marker. The `nomenclature` type is
  `root_required`, so `check --all` errors without it, and 0.1 has no config escape. `init` is the
  command that makes a repository legible to the tool, not a convenience.
- **`max_rows = 35` and `max_chars = 6000` are hard errors in 0.1.** The README states plainly
  that the vocabulary is deliberately small. 0.3 makes them overridable per §4.3. *(0.2: the
  character cap is 3000 and measures the file outside the table's rows -- decision 35.)*
- **`session_context.py`'s `REGENERATE`** is an f-string with no placeholders, and hardcodes the
  skill path. Both disappear when it becomes `doc-marshal index`.
- **`check_structure` re-reads the file from disk** to measure size, though the caller already read
  it. Thread the text through; whole-file measurement is correct, since the note is emitted with
  its frontmatter. *(0.2: the table's rows are excluded from the measurement and the session no
  longer receives the frontmatter -- decisions 35 and 36.)*
- **`check_vocabulary`'s `\b{alias}\b`** misbehaves for an alias with a leading or trailing
  non-word character (`.env`, `C++`) -- and a vocabulary is exactly where those appear.

## 17. Validation

- [x] **V1** -- `doc-marshal check --all` reproduces the prototype's output on the prototype's own
      tree, note for note, with the marker placed in its existing `agent-docs/` directory. *(0.1;
      against the five-type preset the same tree fails on exactly its migration set -- six
      `background` notes, four spec statuses, the `CONTEXT.md` rename and its `Historical`
      column -- and nothing else.)*
- [x] **V1b** -- `doc-marshal init` warns on a `docs/` directory holding `conf.py` or `mkdocs.yml`,
      and says what it found; and every command fails legibly when no marker exists.
- [x] **V1c** -- a repository holding both a Sphinx `docs/` and a marked tree elsewhere validates
      only the marked one.
- [ ] **V2** -- the round-trip test passes: the `standard` preset serializes to TOML, loads back,
      and compares equal. *(0.2)*
- [x] **V3** -- the plugin's hooks validate a note through the engine in the project's virtualenv;
      with no engine installed, SessionStart says so once and PostToolUse stays silent.
- [x] **V4** -- `doctor` reports a deliberate version mismatch between a repo pin and the installed
      engine.
- [x] **V5** -- a real project runs a full `/update-docs` cycle against the extracted tool, with
      the thin SKILL.md, and the agent completes the process without the prose it used to carry.
      *(0.1; to be re-run once MakeRent migrates to the five-type preset.)*
- [x] **V6** -- a fresh session's injected block is under 1000 characters on a 300-note tree.
- [x] **V7** -- `pre-commit run --all-files` blocks a commit carrying an invalid note, and the
      index regeneration fails for re-adding rather than silently staging.

## 18. Known boundaries

What the checks do not see, recorded so nobody reads a clean run as covering them. Each is a
choice or a limit of the parser, not a gap to be discovered. The rules document (`info --rules`)
states only what is checked; this section is its complement.

- **Names.** The kebab-case pattern is ASCII only, so an accented name fails; a name may start
  with a digit; a dotfile fails naming unless it is an exempt tooling name. A nested agent-memory
  file, or both memory files at the docs root, pass without comment.
- **Frontmatter.** The parser reads scalars and dash-item lists and nothing richer, and the block
  opens at the first byte of the file. A folded scalar, a flow list `[a, b]`, a nested mapping, a
  UTF-8 byte-order mark, or a blank line before the opening `---` each reads as "no frontmatter"
  or "unparseable". An empty `https://` passes as a URL.
- **Links.** A `?query` suffix is reported as broken. An HTML `<a href>` and a reference-style
  definition (`[r]: x.md`) are not checked at all.
- **Numbering.** `new` numbers from the working tree, so two worktrees or branches can hand out
  the same number; the collision surfaces on merge as the uniqueness error, and the later note is
  renumbered then.
- **The alias scan.** An indented code block is not a fence and is scanned. A multi-word alias
  is followed across one line break inside a paragraph, never across a paragraph break.
- **Nomenclature.** A second table under `## Terminology` is read as more rows; a `###` inside a
  section is ordinary content; a `NOMENCLATURE.md` under `decisions/` is accepted as the vocabulary
  of that subtree.
- **Enforcement.** `--format github` annotates the file, not a line: the validator reports on
  notes, not positions. Append-only on a `decision` is a convention the tool does not hold
  (decision 44). Vocabulary conformance in code is a review obligation: only the docs tree is
  scanned.
