# The doc types

What each type is for, how it reads, how it changes, and what it must carry. Everything that is
not per-type -- naming, attachments, links, the index, the general frontmatter rules -- is
`doc-marshal info --rules`.

Under each type, the facts list is read from the registry and is what `doc-marshal check`
enforces. The prose after it is how to write the type well; nothing in it is checked.

A type names the reader it serves. One type per document: someone running a procedure does not
want a specification in the middle of it, and someone reading how a feature behaves does not
want a step list. Split instead, and link.

Two columns below decide the most. **Mutability** says whether a change rewrites a doc or appends
to it. **The anchor minimum** is what outside the doc would falsify it -- a repo path for facts
this repo decides, a source for facts it observes -- and it is what makes "which docs does this
diff touch?" a question with an answer. It gives the fields of which a note must carry at least
one; any declared field is legal on any type.

{{types_table}}

The types requiring no anchor are anchored by their own content: a `decision` by its context
section, a `nomenclature` note by the words the repo uses. A `spec` is anchored from `done`
onward, because before that the code it would name need not exist.

There is no index type. The index is generated from every note's `type` and `summary`, so the
summary line is all a reader sees before opening a note; a hand-written index of any kind is an
error.

The examples below illustrate shape, drawn from a generic service project. Match their form, not
their subject.

## `reference`

A fact someone looks up: one subject per note, stated flat, and complete. A reference with three
of five fields is a trap.

Two kinds of fact live here, and the difference is who decided it, not how it reads. Facts this
repo decides -- config fields, event codes, schemas, CLI surfaces, the interfaces we define --
anchor to the code with `code_refs`: if editing code and shipping would change the fact, it is
ours. Facts this repo observes -- part specs, measurements, vendor protocols, third-party
behaviour, research the project draws on -- anchor to where they came from with `source`. A
vendor protocol we implement carries both, and that is the common case.

- Structure follows the thing described: a schema is a table, a protocol is a numbered list of
  messages. No section is required.
- State what is true now. No past tense, and no procedures -- that is a runbook.
- Insight is welcome where it helps a reader use the fact. A choice with live alternatives is a
  `decision`; how a feature behaves as a whole is a `spec`.
- Cite what backs an observed claim, and note the revision. Distinguish specified from measured:
  a vendor's typical value is not what your unit does. Where two sources disagree, give both.

---

## `runbook`

A procedure someone runs: a deploy, a validation, a setup, a credential rotation, a recovery.

- Imperative mood. Literal, copy-pasteable commands: this is the one type where a hardcoded value
  is correct.
- Where the path branches, name the condition before the action. Order steps cheapest and least
  destructive first.
- Say what a step shows when it worked, and what its failure looks like. An escalation criterion
  is time- or condition-based, never "if it still seems wrong".
- No rationale beyond what a step needs to be run safely; link the `spec` or `reference`.
- A runbook with nothing to require says so under `## Prerequisites` in one line.

Structure:

```markdown
# Deploy the payments service

## Prerequisites
What must be true before step one: access, tools, state. One line each.

## Steps
1. `make release` -- prints the version it built.
2. If the smoke check fails, `make rollback` and stop.
```

---

## `decision`

One choice, its context and its consequences: the why of a choice, for someone about to reopen it.

- Reserved for choices with live alternatives or cross-subsystem consequences. Routine
  implementation choices are not recorded; an insight that helps a reader use a fact belongs in
  the reference that states it.
- Append-only. An accepted decision is never edited; a change is a new decision that supersedes
  it, linked both ways. A dead end with no choice left standing is git's to record. Maintenance --
  a heading the shape requires, a repaired link, an `updated` bump -- changes nothing decided and
  is allowed. The validator holds the shape; append-only is yours to hold.
- The alternatives, and why each lost, are the part that stops the question being reopened.
- `doc-marshal new decision <slug>` derives the number, the path and the title. Do not number one
  by hand.

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

---

## `spec`

The behaviour of a feature as a whole, stated so someone can build it, validate it, or learn what
the system is. Where a `reference` is granular, a spec is end to end: it links to the references
that hold the facts its statements rest on, and several specs may point at one reference.

- `status` is a claim about the code, not the writing: `proposed` while nothing is built,
  `in-progress` while code and doc disagree, `done` when they agree.
- Living at every status. When the code changes, rewrite the spec to match. When the spec moves
  ahead of the code, set it back to `in-progress` until the code catches up; the validator warns
  when a `done` spec was edited by a change that touched none of its code, because only the
  author knows which happened.
- Statements, not narrative. Where a statement rests on a fact, link the reference that holds it.
- Give validation items stable identifiers, `V1`, `V2`, so one can be ticked, cited and reported
  without renumbering the rest.
- `## Open questions` holds what is unsettled, one per line. A resolved question is deleted or
  becomes a `decision`; `done` means nothing is open.

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

---

## `nomenclature`

The vocabulary the repo is written in: which word means which thing, and which words are ruled
out. The body is parsed by the alias scan and the nesting check, so its shape is fixed, as the
facts above state.

- Only terms specific to this project. A general programming idea the project uses heavily --
  timeouts, retries, error types -- does not earn a row.
- Be opinionated. Where several words exist for one concept, pick one and rule out the rest in
  `Avoid`; a table of synonyms has recorded the problem rather than fixed it.
- Define what a term is, not what it does, in one line.
- A rename puts the old word in `Avoid` and records itself as a `decision`. Append-only notes are
  never scanned, so the decision keeps its old word unflagged.
- `## Ambiguities` holds live concerns only. A resolved one is deleted or becomes the `decision`
  that resolved it.
- It needs no anchor: a vocabulary is falsified by the words the repo uses, not by a file moving.
- Any directory may add a nested one that refines the root's. `doc-marshal new nomenclature
  <directory>` is enough, since the filename is the type's.
