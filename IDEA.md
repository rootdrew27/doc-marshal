# IDEA.md

1. Consider requiring a hidden file in each directory. This hidden file could contain information analagous to what is stored in the frontmatter of each document; importantly a summary could be kept here. Additionally, this information could be used in INDEX.md or in one form of the `doc-marshal index ...` call.

2. Use an abbreviated name for imports and command line calls. This idea is worth considering as human users will be more prone to use the CLI if the commands are easier to type (e.g. `dm check --all`), but it falls out of favor if a coding agent would struggle to use the abbreviate, rather than the straight-forward and prose-structured `doc-marshal`. 

3. The Claude Code plugin for `doc-marshal` is a secondary feature, and not a first-class offering. 
4. Grant the engine its Claude Code permission from the plugin, not from `.claude/settings.json`. The entries `init --claude-code` writes (`Bash(doc-marshal:*)`, `Bash(uv run doc-marshal:*)`, `Bash(.venv/bin/doc-marshal:*)`) are command prefixes, so they cover only the spellings someone thought of -- an absolute path, `./.venv/bin/doc-marshal`, `python -m doc_marshal`, `poetry run doc-marshal` all still prompt, and a non-interactive session cannot answer (found in the V5 run). A PreToolUse hook in the plugin would instead parse each Bash command, strip any runner or path in front of the executable, and return `permissionDecision: allow` when the program is `doc-marshal` or `python -m doc_marshal`. Strict by construction: refuse any command containing chaining, pipes, redirection or substitution, so `doc-marshal check; rm -rf ~` is never approved the way a prefix rule would. The settings.json entries stay as the fallback for Claude Code without the plugin. Editing notes (`Edit`/`Write` under the docs root) is a separate, user-owned policy; at most `init` could print an opt-in `Edit(<docs-root>/**)` line.

5. Add a convention specifying a folder that stores images, pdfs, etc. (non-markdown) and consider adding tools like pdf extractors to this package so that these files can easily be read. Important note: the `reference` docs will frequently reference files in this folder.

6. Handle mermaid diagrams.

7. An optional `status` on `reference` and `runbook`, absent meaning `done`, for an interface still being defined or a deploy path still being built. Decided against on 2026-09-03: only `spec` carries the lifecycle for now, and a proposed reference is a spec by another name until a real tree shows otherwise.

8. Split the plugin's one general skill, `marshal-the-docs`, into several specialized skills, each for one kind of write to the tree. How to split it is deferred until the general skill has run on real trees.

9. Embrace the nomenclature and use words like: "law", "Clause", "resolution", "ammendment"
    Title — a major division of a legal code, often organized by subject.
    Chapter — a subdivision of a title.
    Part — a subdivision within a chapter or other major division.
    Article — a substantial subdivision, especially common in constitutions and codes.
    Section (§) — one of the primary numbered units of a statute.
    Subsection — a subdivision of a section, often marked (a), (b), etc.
    Paragraph — a smaller numbered or lettered subdivision.
    Clause — a specific provision or condition within a section, paragraph, or sentence.
    Subclause — a subdivision of a clause.


10. Slogan idea: "Doc Marshal, Keep your docs in line..." (picture of a marshal with a smoking gun)

11. The `update-docs` skill should be generalized (it needn't be ran only when work is complete); also, change its name to indicate that it is part of this package (e.g. `marshal-the-docs`). 
    - To do this you should determine how the `process.md` file is rendered and possibly modify it

12. Dogfood it!

13. A setup skill, which would also carry the extra features setup needs, so that installation stops being the thing that constrains the engine. Standing up the project by hand is what makes a zero-dependency install worth defending; a skill that owns setup absorbs that cost, and once it does, the package can take real dependencies instead of re-implementing what they already do -- the hand-rolled frontmatter reader, the subset markdown reader, the TOML writer. Developing against the standard library alone is not a long-term solution. Note the tension with SPEC.md section 9: test 1 (pure Python) is an install-friction argument, and a setup skill is exactly what dissolves it, but test 2 (a dependency must not replace a strictness boundary) is a separate argument and survives -- the subset readers raise on what the convention does not sanction, and PyYAML would not. So the skill unlocks the dependencies whose job is not enforcement, and leaves the parsers where they are until something stricter than PyYAML shows up.

14. Interoperate with OKF (Open Knowledge Format, https://okf.md/spec/). OKF is a directory of markdown files where each concept file carries YAML frontmatter, and it requires exactly one field: `type`. There is no registry of types, unknown keys must be tolerated, and a conforming consumer must tolerate broken cross-links and missing index files. That is the philosophical inverse of this engine -- maximum permissiveness against Tier 1 invariants and decision 52 -- so it is not a competitor but a substrate, and it is converging on our vocabulary from the other direction (`type`, a `status` lifecycle, `stale_after`, `sources`). A marshal tree is already very nearly a valid OKF bundle: every note has a `type`, and `source` is close to OKF's `sources`. The question worth a decision record is what interop is for. Two candidates, and they are not the same feature:
    - **Emit.** A marshal tree validates as an OKF bundle, so a third-party OKF consumer can read it. This is nearly free today and costs us nothing, since OKF's permissiveness means our stricter tree is a subset of what it accepts. The one thing to check is whether our `type` names collide with any conventional OKF ones.
    - **Ingest.** Read a foreign OKF bundle and hold it to our rules. This is the expensive direction and probably the wrong one: OKF has no registry of types, so there is nothing to route on, and "tolerate broken cross-links" is precisely the guarantee we exist to refuse.
    - **Positioning**, which may matter more than either. If OKF becomes the ambient standard for agent-readable markdown, "the validator that actually holds you to it" is a sharper pitch than SPEC section 2's engine-not-convention framing, and the OKF Enforcer Obsidian plugin already occupies that job inside a vault.
    Deferred until a real tree asks for it; noted 2026-09-05 from the comparables research.

15. Take influence from schematter (https://document-schema.org/, Apache-2.0, iwe-org), but do not depend on it. It validates one page against one schema, and says that routing -- deciding which schema governs which page -- is the caller's job, which is exactly the layer this engine is. Delegating shape to it would delete `check_title`, `check_sections` and `check_structure`: 147 lines of 4221, against a Rust binary on the critical path. That fails dependency test 1, and since required sections are a strictness boundary it fails test 2 as well. Four things worth borrowing anyway:
    - **Token budgets rather than character caps.** The nomenclature prose cap is 3000 characters and the stated reason for it is that the note is injected into every session -- a token concern measured in the wrong unit. `tiktoken` has a Rust core, so measuring properly is blocked by the same policy; the cheap win is to state the budget in tokens and choose the character cap to match it.
    - **A binding trace, `--explain`.** `check` reports the violation but never which type bound the note or why, and that is what an agent gets stuck on mid-task.
    - **Converge on their names for the ordering and occurrence semantics of `required_sections`.** Free, and it makes the emit path below mechanical.
    - **Emit, do not consume.** A schematter schema per enabled type, alongside the OKF emit of 13.

16. Make the type definition format a published standard rather than an internal config schema. Most of the mechanism is already designed -- `extends`, per-type shallow merge, `enabled = false`, and the round-trip test that serializes the built-in registry to TOML and loads it back. What this framing adds is that the format should be documented and versioned as something users write against, the way schematter publishes a meta-schema for its schemas. The property that makes it credible is that the standard preset is not privileged: its five types are defined in the same format a user's types are, so `info --dump-toml` on the preset is a worked example rather than a sample, and any facet the preset uses is a facet a user can use. The round-trip test already enforces exactly that, so the work here is documentation and a stable name for the format, not new mechanism. Open: whether the format carries its own version number independent of the package's, which it needs as soon as a user's file has to survive a change to the preset.

17. Anchor to content, not only to paths, so drift is a property of the tree rather than of a diff. Studied `tether` (https://github.com/rootdrew27/tether) on 2026-09-06.

    **The problem.** `affected` compares anchor paths against a diff, so it can only answer "did this change touch a path this note names". Two limits follow:
    - Drift has no memory. A change to the rounding code merged three weeks ago, nobody updated the rounding note, and today on trunk there is no diff -- so nothing in the tool will ever say the note is stale. It stays wrong until someone happens to change that file again.
    - Anchors are coarse. An anchor is a whole file or a whole directory. A note about one function in a 500-line module is flagged by every edit to that module, including edits that cannot affect it. Authors respond by living with the noise or by not anchoring at all -- which is the failure the empty-result message hints at.

    **What tether does.** When a relationship is recorded, it stores the git blob hash of each file's content at that moment; later it hashes the file again and compares. Different hash means the file changed since the relationship was last asserted, no diff required. One end of a relationship can also be a *region* named by what it is -- the `reset_password` function, the `Framing/Checksum` heading -- so only a change inside that region counts.

    **The proposal, in two parts.**
    - *Region entries.* Allow an anchor entry to name a region with a `::` suffix, the delimiter tether chose: `src/auth.py::reset_password`, `docs/proto.md::Framing/Checksum`. Python symbols and markdown headings first; tree-sitter would extend it to any language tether already covers. In diff mode `matches` is unchanged, because the file path still contains the change. A region that no longer resolves is reported the way `check` already reports a file that does not exist -- no new state.
    - *Fingerprints without a database.* Tether needs `.tether/` because a relationship has no natural home. A note has one, and git already holds its history. The freshness check forces every edit to a note to bump `updated`, so the last commit that touched the note is the last time someone asserted "this note is true". At that commit git can give us the content of every path or region the note anchors to. Compare it to the content today: same means aligned, different means the code moved after the note last asserted it. No stored hash, no range, no diff.

    **Worked example.** The rounding note was last edited in commit `a1b2c3` and anchors `src/ledger/rounding.py::round_amount`. The drift check (1) finds the last commit touching the note, (2) extracts `round_amount` from `rounding.py` as it was at that commit, (3) extracts the same function from the working tree, (4) hashes both and compares. It runs on trunk, on any branch, and in a fresh CI checkout, because it needs only history.

    **What it improves.** `affected --stale` (or `check --drift`) gets a trunk-wide answer. The lead check today warns that a `done` spec was "edited while none of its code was", relative to a range; with the fingerprint it can say the stronger thing -- "the code this spec anchors to has changed since the spec last asserted it" -- on any branch. That is the question `requires_from` was trying to ask.

    **Open.** A typo fix to a note bumps its date and so re-asserts every anchor. That is the honest reading of the freshness rule, but it may want a flag or a stated convention.

18. Surface anchors at the moment of the edit, and measure what the spine does not cover. Same study of tether, 2026-09-06.

    **The problem.** The plugin's PostToolUse hook validates a *note* the moment it is written. When an agent edits a *code* file some note anchors to, nothing happens; it learns at pull-request time, from a CI annotation, after the session ended. Tether's team saw the same shape with turn-end reporting: the signal arrives after the agent has mentally finished, reads as a forced reversal, and pre-existing problems repeat every turn with nothing to tell old from new. Their answer is a hook on every tool call that reports only transitions, once, in the call that caused them.

    **Part one: reverse lookup at write time.** Matching already runs in reverse: `affected --paths <file>` lists every note anchored to that file. The hook can run it on every Write or Edit outside the docs root and inject one line -- "this file is anchored by <notes>; confirm they still hold" -- keyed by a session-scoped cache so a second edit to the same file stays quiet. It reuses the existing frontmatter sweep and needs at most a flag that prints nothing when nothing matched.

    *Example.* An agent edits `src/ledger/rounding.py`. The hook injects: "rounding.py is anchored by docs/ledger-rounding.md (reference) and docs/specs/0003-batch-posting.md (spec)". The agent updates them in the same turn instead of meeting the annotation on the PR tomorrow.

    **Part two: a coverage report.** Tether's `coverage` command reports what fraction of tracked files participate in any relationship and lists the ones that do not. The empty `affected` result says "either the change is undocumented or its docs are anchored elsewhere" and cannot tell which. `affected --coverage [<dir>]` can: it lists the tracked files under a directory that no note's spine anchor covers, using the containment matching that already exists. Two uses:
    - On a pull request, over `src/`, the annotations gain "new file with no note", turning a reviewer's hunch into a line in the checks.
    - In a docs run, Stage 6 can state the count of files it deliberately left undocumented, which the process already asks the agent to disclose.

    **Relationship between 17 and 18.** Neither depends on the other; both halves of 18 reuse `matches` and `path_fields` unchanged. 17 sharpens 18: a region-level lookup at edit time tells the agent whether the function it just changed is the one the note is about, and coverage over regions rather than files is more honest about what is documented.
