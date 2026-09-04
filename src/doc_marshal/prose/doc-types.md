# The doc types

This is the **ontology**: what each type serves, how it reads, how it changes, and the frontmatter
particular to it. Everything else -- naming, attachments, links, indexes, prose, the general
frontmatter rules -- is `doc-marshal info --conventions`.

Examples throughout illustrate *shape*, drawn from a generic service project. Match their form,
not their subject matter.

A type names the reader it serves, and nothing else. One type per document: a document that mixes
types serves no reader well, because someone running a procedure does not want a specification in
the middle of it, and someone reading how a feature behaves does not want a step list. Split
instead, and link.

Two columns below are load-bearing. **Mutability** decides whether a change rewrites a doc or appends
to it. **The anchor minimum** is what outside the doc would falsify it -- a repo path for facts this
repo decides, a source for facts it observes -- and it is what makes "which docs does this diff
touch?" a question with an answer. The column gives the fields of which a note must carry *at least
one*: any declared field is legal on any type, and a doc anchored both ways carries both.

{{types_table}}

The types requiring no anchor are anchored by their own content instead: a `decision` by its
context section, and a `nomenclature` note by the words the repo actually uses. A `spec` is anchored
from `done` onward, because before that the code it would name need not exist.

**Structure is enforced where a type has one.** Every note has exactly one H1, and it is the
first heading; a numbered note's H1 starts with its number. A type that declares required
sections must carry each of them, once, in that order, with something written under each once
HTML comments are stripped; other sections may appear anywhere. `doc-marshal new` writes exactly
the required sections, so a scaffold is the spine and the writing is what makes it pass. A
`nomenclature` note is stricter still, since its body is parsed. A `reference` has no required
sections at all.

---

## `reference`

A fact someone looks up. Granular and specialized: one subject per note, stated flat.

Two kinds of fact live here, and the difference is **who decided it**, not how it reads:

- **Facts this repo decides.** Config fields and their meaning, event codes, schemas, CLI surfaces,
  the interfaces and message formats we define. If we could change the fact by editing code and
  shipping, it is ours, and the note anchors to that code with `code_refs`.
- **Facts this repo observes.** Part numbers and their specs, measured waveforms, pin-outs, vendor
  protocols, operating-system and third-party behaviour, research the project draws on. Nothing we
  ship changes them; a new measurement, a vendor revision or a replaced part does. The note anchors
  to where the fact came from with `source`.

A note carries both when both apply, and that is the common case rather than an exception: a vendor
protocol we implement anchors to the datasheet *and* to the client that speaks it. Code
contradicting a vendor spec is a bug in the code, not a stale doc, and the two anchors are what let
either side be checked.

- Structure follows the thing described, not a story. Tables and definition lists over paragraphs.
  No sections are required: a schema is a table, a protocol is a numbered list of messages, and
  a heading imposed on either would be a heading with nothing under it.
- No procedures ("to do X, run Y") -- that is a runbook.
- State what is true now. A reference has no past tense.
- Completeness matters more than prose quality: a reference with three of five fields is a trap.
- Insight is welcome where it helps a reader use the fact -- the constraint behind a limit, the
  invariant a schema protects -- but a choice with live alternatives is a `decision`, and how a
  feature behaves as a whole is a `spec`.
- **Cite what backs every non-obvious observed claim.** A number with no source is the failure mode:
  nobody can tell a datasheet figure from a bench measurement from a guess that hardened into fact.
  Where two sources disagree, say so and give both -- the disagreement is the useful part.
- Distinguish **specified** from **measured**. A vendor's typical value is not what your unit does.
  Note the revision of anything you cite; datasheets get revised and the old figure stops being true.

Examples: `services/payments/api.md`, `platform/registry-schema.md`, `pumps/controller-spec.md`.

`source` entries are URLs, or repo-root-relative paths to an attachment or to another note that
carries the measurement -- **never** a code path, which is what `code_refs` is for. Attachments keep
their published filenames and live in the docs root's one `assets/` directory, which is exempt
from validation.

---

## `runbook`

A procedure someone runs: deploying a package, validating an application, setting up a workstation
or a service, rotating a credential, recovering from a known failure.

- Imperative mood, second person implied. "Confirm it", "Take the camera from the app".
- Literal commands, exact and copy-pasteable. This is the one type where hardcoded values are correct.
- Decision-tree shape where the path branches: *if X then Y*. Name the condition before the action.
- Order steps by what to try first, cheapest and least destructive first.
- Say what a step should show when it worked, so the reader knows to go on rather than guess.
- Where a step can fail, say what the failure looks like and what to do about it. Any escalation
  criterion is **time- or condition-based**, never "if it still seems wrong".
- No rationale beyond what a step needs to be run safely -- link the `spec` or `reference` instead.

Two sections are required, in this order, and others may follow or sit between them:

```markdown
# Deploy the payments service

## Prerequisites
What must be true before step one: access, tools, state. One line each.

## Steps
1. `make release` -- prints the version it built.
2. If the smoke check fails, `make rollback` and stop.
```

`## Prerequisites` is the check-before-you-run material, in one place. A runbook with nothing to
require says so in one line rather than deleting the section.

Examples: `services/payments/deploy.md`, `platform/provisioning/*`, `local-testing.md`.

---

## `spec`

The behaviour of an application or feature **as a whole**: what it does, stated so that someone
can build it, validate it, or read it to learn what the system is. Overarching, where a `reference`
is granular: a spec says what a thing does end to end, and links to the references that hold the
facts its statements rest on. Expect a spec to point at several references, and a reference to be
pointed at by more than one spec.

- Carry a `status`: `proposed` while nothing is built, `in-progress` while the code and the doc do
  not yet agree, `done` when they do. The status is a claim about the code, not about the writing.
  It is required in the note; `doc-marshal new spec` writes `proposed` when none is given.
- **Living at every status.** When the code changes, the spec is rewritten in place to match; when
  the spec is rewritten ahead of the code, its status goes back to `in-progress` until the code
  catches up. The validator warns when a `done` spec was edited in a change that touched none of
  its code, because only the author knows which of the two happened.
- Keep validation items enumerated with stable identifiers (`V1`, `V2`, ...) so an individual item
  can be ticked off, cited and reported on without renumbering the rest. An `in-progress` spec with
  nothing left unticked is either `done` or missing an item.
- Statements, not narrative. Where a statement rests on a fact, link the reference that holds it
  rather than restating the fact here.
- `## Open questions` holds what is still unsettled, one per line, while the spec is `proposed`
  or `in-progress`. A resolved question is deleted or becomes a `decision`. The section is
  optional, and a `done` spec may not have anything under it: `done` means nothing is open.

`## Overview`, `## Behavior` and `## Validation` are required, in that order; other sections may
appear anywhere.

Structure:

```markdown
---
type: spec
updated: 2026-08-07
summary: How a payment retry is scheduled, parked and escalated.
status: in-progress
code_refs:
  - src/payments/retry.py
---

# Payment retries

## Overview
The feature in a paragraph: what it is for, and where it starts and stops.

## Behavior
What it does, as statements, each linked to the reference that justifies it.

## Validation
- [x] **V1** -- a failed charge is retried on the schedule `retry.backoff` declares.
- [ ] **V2** -- the fifth failure parks the payment and notifies the owner.

## Open questions
- Does a parked payment expire, and after how long?
```

`code_refs` is required once the status is `done` and optional before it: a `proposed` spec names
no code because none exists, and paths arrive as the work lands. A spec anchored to nothing is off
the drift spine, which is the correct statement about a feature that is not built yet and the wrong
one about a feature that is.

---

## `decision`

One architectural decision, its context, and its consequences. This is where the **why** of a
choice lives.

- Lives in the docs root's `decisions/`, named `NNNN-kebab-slug.md`, where `NNNN` is the highest
  existing number plus one, zero-padded to four. If two branches collide on a number, renumber the
  later one on merge. `doc-marshal new decision <slug>` derives all of that; do not number one by hand.
- **Reserved for choices with live alternatives or cross-subsystem consequences** -- the ones someone
  will reopen. Routine implementation choices are not recorded; an insight that helps a reader use
  a fact belongs in the reference that states it.
- **Append-only.** Never edit an accepted decision. If it changes, write a new decision that
  supersedes it and link both directions. A dead end that was abandoned without a choice left
  standing is recorded by git, not here. Maintenance is not an edit of the decision: adding a
  heading the shape requires, repairing a link, or bumping `updated` when an anchor moves changes
  nothing that was decided, and is allowed. Append-only is a convention the validator does not
  enforce; what it enforces is the shape.
- Include the alternatives considered and why each was rejected. That is the part that stops the
  question being reopened.

All four sections below are required, in that order, and each says something; other sections may
appear anywhere. The title starts with the note's number.

Structure:

```markdown
---
type: decision
updated: 2026-08-07
summary: Why a repeatedly-failing retry parks instead of exiting.
status: accepted
code_refs:
  - src/payments/retry.py
---

# NNNN -- <the decision, as a statement>

## Context
What forced a choice. The constraint, the failure, the requirement.

## Decision
What was decided, in the active voice.

## Alternatives considered
Each one, and the specific reason it lost.

## Consequences
What this makes easy, what it makes hard, and what it commits us to.
```

`supersedes:` and `superseded_by:` name the other decision's filename. A decision that names its
replacement says `status: superseded`, and a note is never born superseded -- `doc-marshal new`
refuses that status. Neither field may name the note itself. `code_refs` is optional.

---

## `nomenclature`

The **vocabulary** the repo is written in: which word means which thing, and which words are ruled
out. `doc-marshal info --conventions` §8 states the rules; this is how the type reads.

- Lives at `NOMENCLATURE.md` -- the docs root carries one, and any directory may add one that refines it.
  The filename is the type's, so `doc-marshal new nomenclature <directory>` is enough.
- **Only terms specific to this project.** Before adding a row, ask whether the concept is unique to
  this domain or is a general programming idea the project happens to use heavily. Only the former
  belongs. Timeouts, retries and error types do not, however central they are.
- **Be opinionated.** Where several words exist for one concept, pick one and rule out the rest in
  `Avoid`. A vocabulary that lists synonyms without choosing between them has recorded the problem
  rather than fixed it.
- **Define what a term *is*, not what it does**, in one line. "A request for payment sent to a
  customer after delivery" -- not two sentences on when invoices are generated.
- A rename puts the old word in `Avoid` and records itself as a `decision`; that is the history.
  Append-only notes are never scanned, so a decision written in the old word is not flagged.
- `## Ambiguities` holds **live** concerns only -- a term two people still use differently, a name
  known to be overloaded. A resolved one is deleted, or becomes the `decision` that resolved it.
  This is not an archive; the size cap makes that concrete.
- Needs no anchor. A vocabulary is falsified by the words the repo uses, not by a file moving, and
  anchoring it to code would flag it on every unrelated change. An anchor is legal here as on any
  type, and is validated when present.

The type is the one whose body is **parsed** -- the sections, the columns and the caps are fixed and
machine-checked, because the alias scan and the nested-collision check read the table. Reformatting
it does not degrade those checks, it silently disables them. What the parser holds the table to:

- One row per term. A term defined twice, in any case, is an error; so is a word listed under
  `Avoid` that is also a term, since a word is defined or ruled out, not both. A nested note
  redefining an ancestor's term is caught in any case too.
- A literal pipe in a cell is written `\|`, as GitHub reads it.
- The prose cap counts the body outside the table's rows; the frontmatter is not counted, since
  a session never sees it.

Boundaries the parser does not police: a second table under `## Terminology` is read as more rows,
an `###` inside a section is ordinary content, and a `NOMENCLATURE.md` under `decisions/` is
accepted as the vocabulary of that subtree.

---

## There is no index type

Indexes are generated, never written -- `doc-marshal info --conventions` §5 states that rule and
why. What it means for writing a note:

- A note is discoverable **only** if its `summary:` is good, because the generated index shows
  nothing else. Treat that line as the most load-bearing sentence in the doc.
- Cross-references are inline links, made where the statement that needs them is. A note does not
  end with a list of its neighbours: an index says *what exists*, and a link in a sentence says
  *why you would go there*.
