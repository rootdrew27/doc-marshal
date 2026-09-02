# The doc types

This is the **ontology**: what each type serves, how it reads, how it changes, and the frontmatter
particular to it. Everything else -- naming, attachments, links, indexes, prose, the general
frontmatter rules -- is `doc-marshal info --conventions`.

Examples throughout illustrate *shape*, drawn from a generic service project. Match their form,
not their subject matter.

One type per document. A document that mixes types serves no reader well: someone executing a
procedure does not want rationale in the middle of it, and someone deciding whether an approach was
already tried does not want to read a reference table. Split instead, and link.

Two columns below are load-bearing. **Mutability** decides whether a change rewrites a doc or appends
to it. **The anchor** is what outside the doc would falsify it -- a repo path for facts this repo
decides, a source for facts it observes -- and it is what makes "which docs does this diff touch?" a
question with an answer. The column gives each type's required *minimum*: any declared field is
legal on any type, and a doc anchored both ways carries both.

{{types_table}}

The types requiring no anchor are anchored by their own content instead: a `decision` by its
context section, a `history` entry by describing code that may no longer exist, a `spec` by
describing work that may not exist yet, and a `context` note by the words the repo actually uses.

---

## `reference`

Facts **this repo decides**, enumerated. Config fields and their meaning, event codes, registry
schemas, CLI surfaces, the interfaces and message formats we define. If we could change the fact by
editing code and shipping, it is a `reference`.

- Structure follows the thing described, not a story. Tables and definition lists over paragraphs.
- No procedures ("to do X, run Y") -- that is a runbook. No rationale -- that is an explanation.
- State what is true now. A reference doc has no past tense.
- Completeness matters more than prose quality: a reference with three of five fields is a trap.

Examples: `services/payments/api.md`, `platform/registry-schema.md`.

Add `source` as well for any fact here that came from outside the repo -- a value you took from a
datasheet, a limit a vendor imposed on your interface. A protocol you did not author is
`background` even when you implement it; see below.

---

## `background`

Facts **this repo observes**, which it did not author and cannot change by shipping: part numbers and
their specs, measured waveforms, pin-outs, wiring, vendor protocols, operating-system and protocol
background.

- Same voice as `reference` -- flat, enumerative, present tense, no procedures, no rationale. The
  difference is not how it reads, it is **who decided the fact**.
- **The routing test: does this repo *decide* this fact, or *observe* it?** A fact you could change by
  editing code is a `reference`. A fact that only a new measurement, a vendor revision, or a replaced
  part could change is `background`.
- **A vendor protocol you implement is still `background`**, and so is a world fact your code
  *encodes* -- a flicker frequency in a profile file, a timeout derived from a datasheet limit. You
  author the implementation, not the protocol; editing the value makes the *value* wrong, not the
  measurement. Both carry `source` for the fact and `code_refs` for the code. Do not route either to
  `reference` on the grounds that your code could contradict it: code contradicting a vendor spec is
  a bug in the code, not a stale doc, and `reference` would make the vendor anchor optional exactly
  where a vendor revision is the likeliest thing to invalidate the doc.
- **Cite what backs every non-obvious claim.** A number with no source is the failure mode of this
  type: nobody can tell a datasheet figure from a bench measurement from a guess that hardened into
  fact. Where both exist and disagree, say so and give both -- the disagreement is the useful part.
- Distinguish **specified** from **measured**. A vendor's typical value is not what your unit does.
- Note the revision of anything you cite. Datasheets get revised and the old figure stops being true.

Examples: `pumps/controller-spec.md`, `sensors/wiring.md`.

`source` entries are URLs, or repo-root-relative paths to an attachment or to another note that
carries the measurement -- **never** a code path, which is what `code_refs` is for. Add `code_refs`
as well whenever this repo implements against, encodes, or depends on the facts recorded here; that
is the common case, not an exception, and it is what puts the doc on the drift spine alongside its
vendor anchor.

Attachments keep their published filenames and live in the docs root's one `assets/` directory,
which is exempt from validation.

---

## `runbook`

A procedure someone runs, often while something is broken.

- Imperative mood, second person implied. "Confirm it", "Take the camera from the app".
- Literal commands, exact and copy-pasteable. This is the one type where hardcoded values are correct.
- Decision-tree shape where the path branches: *if X then Y*. Name the condition before the action.
- Escalation criteria must be **time- or condition-based**, never "if it still seems wrong".
- Say up front what the system already tried automatically, so the operator does not repeat it.
- Order steps by what to try first, cheapest and least destructive first.

Examples: `services/payments/retry-runbook.md`, `platform/provisioning/*`.

---

## `explanation`

Why the system is shaped the way it is. Invariants, the constraint that forced the design, what
would break if you changed it.

- Connective prose. This is the type where paragraphs earn their place.
- Name the invariant explicitly, and name what violates it. An invariant a reader cannot check is
  not documented.
- Record rejected approaches *as part of the argument* -- "the obvious approach was tried and
  rejected, because <the specific property that made it fail>" -- rather than as a separate list.
  The reason must name a property, not a preference.
- Distinguish implemented from validated from deployed. Never let a reader infer that a described
  mechanism is running in production when it is not.
- No commands. No field-by-field enumeration.

---

## `decision`

One architectural decision, its context, and its consequences.

- Lives in the docs root's `decisions/`, named `NNNN-kebab-slug.md`, where `NNNN` is the highest
  existing number plus one, zero-padded to four. If two branches collide on a number, renumber the
  later one on merge. `doc-marshal new decision <slug>` derives all of that; do not number one by hand.
- **Reserved for choices with live alternatives or cross-subsystem consequences** -- the ones someone
  will reopen. Routine implementation choices are explained, not recorded.
- **Append-only.** Never edit an accepted decision. If it changes, write a new decision that
  supersedes it and link both directions.
- Include the alternatives considered and why each was rejected. That is the part that stops the
  question being reopened.

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

## Related
```

`supersedes:` and `superseded_by:` name the other decision's filename. `code_refs` is optional.

---

## `spec`

Work described before it exists, or built but not yet validated. The type that must be reconciled
when reality catches up.

- Carry an explicit `status`: `proposed`, `building`, `shipped-unvalidated`, or `done`.
- Keep pending validation items enumerated with stable identifiers (`V1`, `V2`, ...) so an individual
  item can be ticked off, cited, and reported on without renumbering the rest. A reader must be able
  to tell built-and-verified from built-but-unvalidated from not-built.
- When shipped work lands, **reconcile in place**: update `status`, tick off the items now validated,
  and correct anything the implementation did differently from the plan.
- When everything has shipped **and** validated, convert the doc to an `explanation` of the built
  system: strip the plan scaffolding, change `type`, and keep the invariants and rejected approaches.
  The original plan stays recoverable from git.

`code_refs` is **optional and expected to arrive late**: a `proposed` spec names no code because
none exists, and paths are added as the work lands -- by `shipped-unvalidated` the spec should name
what was built.

---

## `history`

The project's memory: what we tried, what broke, what we measured, what we ruled out.

- One `history.md` per subsystem folder, e.g. `services/payments/history.md`.
- **Appended, never rewritten.** Add a new dated entry (`## 2026-08-07 -- <what happened>`) at the
  end. Earlier entries stay exactly as written even when later work proves them wrong -- being wrong
  at the time is the record.
- Verbose prose is correct here. Include the numbers, the symptom as observed, the wrong hypothesis
  and why it was wrong.
- A large investigation may get its own note in the same folder, dated in the filename --
  `load-test-findings-2026-07-21.md` -- and linked from `history.md`. Those notes are immutable
  once written; a later run adds a new one rather than editing.
- The filter: does someone need this **without** knowing to go looking in `git log`? If the answer is
  no, leave it in git.

`code_refs` is optional -- history spans code that may no longer exist.

---

## `context`

The **vocabulary** the repo is written in: which word means which thing, and which words are ruled
out. `doc-marshal info --conventions` §8 states the rules; this is how the type reads.

- Lives at `CONTEXT.md` -- the docs root carries one, and any directory may add one that refines it.
  The filename is the type's, so `doc-marshal new context <directory>` is enough.
- **Only terms specific to this project.** Before adding a row, ask whether the concept is unique to
  this domain or is a general programming idea the project happens to use heavily. Only the former
  belongs. Timeouts, retries and error types do not, however central they are.
- **Be opinionated.** Where several words exist for one concept, pick one and rule out the rest in
  `Avoid`. A vocabulary that lists synonyms without choosing between them has recorded the problem
  rather than fixed it.
- **Define what a term *is*, not what it does**, in one line. "A request for payment sent to a
  customer after delivery" -- not two sentences on when invoices are generated.
- `Historical` is for words that *used* to mean the term. They are never flagged; they exist so a
  reader meeting an old word in an append-only note can resolve it. A rename moves words from
  `Avoid` to `Historical`, and records itself as a `decision`.
- `## Ambiguities` holds **live** concerns only -- a term two people still use differently, a name
  known to be overloaded. A resolved one is deleted, or becomes the `decision` that resolved it.
  This is not an archive; the size cap makes that concrete.
- No `## Related`, and no `code_refs`. A vocabulary is falsified by the words the repo uses, not by
  a file moving, and anchoring it to code would flag it on every unrelated change.

The type is the one whose body is **parsed** -- the sections, the columns and the caps are fixed and
machine-checked, because the alias scan and the nested-collision check read the table. Reformatting
it does not degrade those checks, it silently disables them.

---

## There is no index type

Indexes are generated, never written -- `doc-marshal info --conventions` §5 states that rule and
why. What it means for writing a note:

- A note is discoverable **only** if its `summary:` is good, because the generated index shows
  nothing else. Treat that line as the most load-bearing sentence in the doc.
- Cross-references go in `## Related`, where each link carries a reason. That is connectivity, not
  indexing -- an index says *what exists*, `## Related` says *why you would go there next*.
