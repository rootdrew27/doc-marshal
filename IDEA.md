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

13. A setup skill, justified by onboarding rather than by dependencies. The original entry claimed that owning setup is what would let the package take real dependencies. That was wrong, and why it was wrong is worth keeping: the plugin's hooks never import the engine. They run the resolved console script as a subprocess, so its dependencies are resolved by the interpreter named in that script's shebang, and the hook's own ambient `python3` never sees them -- it cannot import `doc_marshal` at all, today, while the hooks work. Under the *earlier* design, the one SPEC.md section 10 records dropping on 2026-09-02, the plugin vendored the engine and the ambient interpreter did import it; stdlib-only was genuinely forced then. Dropping that draft removed the justification and nobody re-audited, so the dependency policy outlived its reason. What the skill is actually for: the `MISSING_ENGINE` dead end, where a session is told the docs root is unvalidated and handed a manual task; the enforcement points of section 12 that most adopters never wire; and project managers whose environment the hooks cannot see, which is the failure that looks most like success. Designed on 2026-09-07, built, and removed the same day: each of those three justifications turned out to be answerable in the engine instead. `MISSING_ENGINE` now states the situation and names no action; `init --pre-commit --ci` wires the enforcement points at the version that enforces them; the invisible-environment case is documented in the README and reported by `doctor`. What was left for a skill was one install command, and 74 lines of prose restating flags it did not own. Recorded in SPEC.md section 19.

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
