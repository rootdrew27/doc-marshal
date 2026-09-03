# Conventions for a doc-marshal docs tree

These are the rules that are not per-type. `doc-marshal check` is their enforcement, and both come
from the same installed package, so they cannot disagree. For what each type is for, read
`doc-marshal info <type>`; for how to update the tree after a code change, `doc-marshal info --process`.

The **docs root** is the directory holding the `{{marker_name}}` marker. Every path below is
relative to it unless it says otherwise. One repository has one docs root.

---

## 1. What is a note

A note is a markdown file under the docs root. Notes are what the convention governs; everything
else is either an attachment or infrastructure.

Not notes, and never validated or indexed:

| Path | Why |
| --- | --- |
| `{{assets_dirname}}/**` | attachments -- see §2 |
| `{{index_name}}` | generated output -- see §5 |
| {{memory_names}} | agent-memory files, not documentation |
| `{{marker_name}}` | the marker that names this directory the docs root |
| {{excluded_dirs}} | tooling and metadata |

**There is no `README.md` anywhere under the docs root**, and one is an error: it is a
hand-maintained index by another name, which §5 bans and explains. A lower-case `index.md` is an
error too, caught by name rather than validated as an ordinary note -- "missing frontmatter" would
not tell you that the generated index is `{{index_name}}` and this file should be deleted or renamed.

## 2. The `{{assets_dirname}}/` directory

The docs root **may** have one `{{assets_dirname}}/` directory. It is optional, and there is at most one.

- **It holds only non-markdown files** -- PDFs, images, spreadsheets, exports.
- **It is exempt from validation entirely.** Nothing inside it is a note. Naming, frontmatter,
  links, and folder names are all unchecked, at any depth.
- **Never rename or reorganize anything under `{{assets_dirname}}/`.** An attachment keeps the filename its
  source gave it: that name is how you re-find the document and confirm its revision, and anchors
  (§4) point at these files by name. §3's naming rule does not reach inside, so folders here may be
  named however the material warrants.
- The exemption is **positional**: only the `{{assets_dirname}}/` directory at the docs root. A nested one
  elsewhere is not the convention and is not exempt.

Two departures are **errors**, reported by a sweep (`doc-marshal check --all`) since they are facts
about the tree rather than about a note: a markdown file inside `{{assets_dirname}}/`, which is never
validated or indexed, and an `{{assets_dirname}}/` directory anywhere but the docs root.

## 3. Naming

Notes and the folders holding them are kebab-case: `^[a-z0-9]+(-[a-z0-9]+)*$`. A filename reads as
its subject, not as a sentence -- `retry-policy.md`, not `how-the-retry-policy-works.md`.

Exempt: everything under `{{assets_dirname}}/` (§2), the fixed-name files in §1, and any filename a type
claims outright -- today {{fixed_names}}. That last exemption is read off the registry, so an
upper-case name no type claims is still an error.

A numbered type carries a `NNNN-` prefix -- see §7.

Rename a note only when its subject has become something else. A naming error that a change did not
cause is not a reason to rename; a rename breaks every inbound link, so it is the most disruptive
edit available and needs approval.

## 4. Frontmatter

Every note carries frontmatter: scalar fields and dash-item lists, nothing richer. Three fields are
always required:

| Field | Rule |
| --- | --- |
| `type` | one of the enabled types -- `doc-marshal info` lists them |
| `updated` | ISO date (`YYYY-MM-DD`) of the last edit. Never a future date, and bumped whenever you edit the note: a note the change touched whose date is earlier than the day the change began is an error |
| `summary` | one line, max {{summary_max}} characters, stating what the doc is for |

`summary` is the only prose the generated index shows, so a note without a good one is effectively
undiscoverable.

### Anchors

Every **living** note declares what outside itself would falsify it. This is what keeps "which docs
does this diff touch?" answerable, and no note may satisfy the rule by omitting the field.

Which field a note carries follows from **authorship**: a repo-path field for facts this repo
decides, a source field for facts it observes, both when a note holds both kinds. A type's minimum
is the set of fields of which a note must carry **at least one**. The table is the registry the
validator enforces from, so it states the requirement rather than describing it.

{{anchor_table}}

- **Every path in frontmatter is written from the repo root** -- never from the docs root and never
  absolute. One rule for every field. Paths must resolve, with **exact spelling**: a
  case-insensitive filesystem does not make `Src/` a match for `src/`, because CI's will not. And a
  path names something **strictly inside** the repository: `.` is not an anchor, since a note the
  whole repository falsifies is anchored to nothing. A directory inside it is fine.
- The table gives each type's **minimum, not its permitted set.** Any declared field is allowed on
  **any** type and is validated whenever present.
- A type may be anchored only **from a status onward**; `doc-marshal info <type>` says so where it
  applies. A note in that status edited by a change that touched none of its anchored code is a
  warning, because the doc may now lead the code and its status would no longer be true.
- **Whenever a note states a fact that came from outside the repo, it carries a source anchor** --
  on any type. A note describing a third-party protocol our code implements carries both: the source
  for the spec, the repo path for the implementation. Do not drop one for tidiness.
- A `docs-path` field must resolve **inside** the docs root. Code belongs in a `repo-path` field;
  pointing a source at a source file would anchor a note while keeping it off the drift spine.
- **The drift spine** is the set of fields that resolve as `repo-path` -- today {{spine}}.
  `doc-marshal affected` matches those, and only those, against a diff.

Per-type extras (`status`, supersession fields) are shown by `doc-marshal info <type>`.

A note anchored to code:

```yaml
---
type: reference
updated: 2026-08-07
summary: How the sync worker chooses between its two ingest modes.
code_refs:
  - src/ingest/sync_worker.py
  - config/ingest.yaml
---
```

A note about a fact we observe rather than decide. It carries `source` because we did not author
the register map, and `code_refs` as well because we implement against it:

```yaml
---
type: reference
updated: 2026-08-07
summary: Modbus register map for the pump controller, as specified and as observed.
source:
  - docs/assets/pump-controller/protocol-spec-rev-c.pdf
  - docs/pumps/bench-measurements.md
code_refs:
  - src/pumps/modbus_client.py
---
```

## 5. Indexes

There is exactly **one** index, `{{index_name}}` at the docs root, and it is **generated** by
`doc-marshal index` from the `type:` and `summary:` of every note. Never edit it by hand.

The name is upper-case so it does not read as an ordinary note: everything else in the tree is
kebab-case, so `{{index_name}}` announces at a glance that it is machine-written. It also sorts to the
top of a directory listing, where a front door belongs.

Do not write any other index: no `README.md` (§1), and no tree, folder listing or "contents of this
directory" section in an agent-memory file or a note. **A committed listing of what a folder contains
is a file whose only job is to agree with the filesystem, and it stops doing that silently.** That
sentence is the whole reason there is one generated index and nothing else; an ad-hoc structural view
comes from `git ls-files`.

Regeneration is **whole-tree by construction**: the builder reads every note, and one missing `type`
or `summary` blocks the whole file rather than being rendered around, since a partial index silently
under-describes the docs.

Regenerate whenever the note set changes -- a note created, renamed or deleted, or a `type` or
`summary` edited. The pre-commit hook regenerates it and fails the commit for re-adding, the way
formatters do, and CI checks it again. A stale index is a warning in CI, never a failure -- the notes
are the source of truth and the index is derived. When the builder refuses because of a note outside
the change at hand, leave it: report which note blocked it rather than fixing docs you did not touch.

## 6. Links

- **Relative markdown links only**: `[retry runbook](../services/payments/retry-runbook.md)`.
  Wikilinks (`[[...]]`) are not a link style here. Absolute paths are not either.
- Link **inline, on first mention** of a concept that has its own note -- once per section, not
  every occurrence. This is the tree's connectivity: an index says what exists, a link in a
  sentence says why you would go there next. A note does not end with a list of its neighbours.
- Heading anchors in links must resolve.

## 7. Numbered notes

A numbered type lives in the folder the registry names for it, as `NNNN-kebab-slug.md`, where `NNNN`
is the highest existing number plus one, zero-padded to four. Numbers are unique; if two branches
collide, renumber the later one on merge.

Do not read the directory and add one by hand: `doc-marshal new <type> <slug>` derives the number,
the location and the `NNNN -- ` title prefix, which is every part of this rule a script can apply
more reliably than a person can.

## 8. Nomenclature notes

These conventions govern the **form** of the tree. A `nomenclature` note governs its **vocabulary** --
which word means which thing, and which words are ruled out. The two do not overlap, and neither
overrules the other: a note can satisfy every rule here and still be written in the wrong words.

The vocabulary binds **documentation and code alike**. Only the docs tree is scanned, because a
third-party library routinely hands you a banned word as the literal name of a field or a method,
and renaming code to satisfy a text search is worse than the drift it fixes. Conformance in code is
a review obligation, in the sense of §10.

### Placement

- **The docs root carries one.** Its absence is an error.
- **At most one per directory**, and every one below the root **refines the nearest one above it**.
  Siblings are allowed.
- **A nested note only adds.** Defining a term an ancestor already defines is an error. One word
  has one meaning across the repo; a subsystem that needs a different concept needs a different
  word, not the same word locally redefined.

### Shape

The body is data as much as prose -- other checks parse it -- so its shape is fixed and every
departure is an error. `doc-marshal info nomenclature` states the exact sections, columns and caps.

- **`Definition`** says what the term *is*, in one line. Not what it does.
- **`Avoid`** lists the aliases ruled out, comma-separated. These are scanned. A renamed term's
  old word goes here too; the `decision` that renamed it is the history, and append-only notes
  are never scanned, so old decisions keep their old words unflagged.
- Say "no aliases" with a dash. A blank cell reads as an unfinished row.

Only terms **specific to this project** earn a row. General programming concepts do not, however
heavily the project uses them. Be opinionated: where several words exist for one concept, pick one
and rule out the rest.

### Size

A nomenclature note at the docs root is **emitted into every session**, so its size is a cost paid on
every run rather than only when someone opens it. Two caps, each an error and each bounding one
thing: the table's **rows**, and the **characters outside the table** -- frontmatter, headings and
the prose sections. Neither is met by squeezing the other, and the session pays for both. A
definition's length is capped as well. When the table is full, a term that has stopped earning its
place comes out before a new one goes in.

### Enforcement

Using a word from an `Avoid` column is a **warning**, never an error. The scan is a word match and
cannot see intent, so a false positive must not block a commit. Two exemptions, both structural:

- **Code spans and fenced blocks are skipped.** Backticks are how you say a banned word is a
  literal name rather than a concept.
- **Append-only types are skipped.** Their wording cannot lawfully be corrected, so flagging it
  would produce warnings nobody is permitted to act on. This follows from the type's mutability in
  the registry, not from a list of names, so a future append-only type inherits it.

## 9. Prose

- Sentence case in headings. The H1 is the human title, so it reads as prose even though the
  filename is kebab-case.
- Imperative mood in instructions.
- Describe values by role, and name the file that owns them, rather than embedding the number:
  "once per `worker.poll_interval` (see the config template that declares it)", not "every 30
  seconds". Runbooks are the exception -- an operator needs a literal, runnable command.
- Say what is true and what is not yet true. Where the docs distinguish implemented-and-unit-tested
  from running-in-production, preserve the distinction.
- Every factual claim traces to code or config, not to another doc -- another doc may be the thing
  that drifted.

## 10. Enforcement

These rules are authoritative whether or not a script can check a given one. Some are
machine-checked and some are not, and the split is worth knowing so nobody reads a clean validator
run as proof that a note follows the convention.

**Machine-checked** (`doc-marshal check`): §1's non-notes and the README ban, §2's attachment
departures, §3's naming, §4's required fields, anchor minimums, resolution by kind, date sanity and
per-type `status`, §6's link style and resolution including heading anchors, §7's naming and number
uniqueness, §8's placement, sections, columns, caps and additive-only rule.

**Convention only, checked by a human or a reviewing agent**: §9, §8's conformance in
code, §6's "inline on first mention" and its ban on trailing neighbour lists, and §5's ban on
hand-written listings inside agent-memory files. A rule being unenforceable does not make it
optional -- it makes it a review obligation.

Of what the validator reports, errors fail the run and warnings never do. Everything a script can
judge on shape alone is an error. The two warnings are the rules that judge meaning: a note
anchored from its status onward that was edited while none of its code was (§4), and §8's alias
scan. There is no inline suppression and no severity configuration: whatever the registry says is
enforced completely, and everything configurable lives in `{{marker_name}}` where review can see it.

### Where enforcement runs

| When | What runs | Effect |
| --- | --- | --- |
| every write to a note | `doc-marshal check <that file>`, via the Claude Code plugin's PostToolUse hook | reports into the session; never blocks |
| every `git commit` | `doc-marshal check` on staged notes, then `doc-marshal index`, via the pre-commit framework | errors block; a regenerated index fails the hook for re-adding |
| every pull request | `doc-marshal check --all --format github`, `doc-marshal index --check` | errors fail the build, each on the file it names; a stale index warns |
| every pull request | `doc-marshal affected --format github` | annotates anchored notes; never fails |

A fifth point is supply, not enforcement: at **session start**, the plugin injects the index
preview, the root nomenclature note, and the compact type list, so a session knows what exists and what
to call it before it writes anything. `doc-marshal session-context` prints the same.

Neither pull-request job takes a `paths:` filter. Half of what they check is whether anchors still
resolve, and those break in the change that renames or deletes the code -- which by definition
touches no documentation.
