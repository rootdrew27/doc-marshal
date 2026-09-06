# IDEA.md

1. Consider requiring a hidden file in each directory. This hidden file could contain information analagous to what is stored in the frontmatter of each document; importantly a summary could be kept here. Additionally, this information could be used in INDEX.md or in one form of the `doc-marshal index ...` call.

2. Use an abbreviated name for imports and command line calls. This idea is worth considering as human users will be more prone to use the CLI if the commands are easier to type (e.g. `dm check --all`), but it falls out of favor if a coding agent would struggle to use the abbreviate, rather than the straight-forward and prose-structured `doc-marshal`. 

3. The Claude Code plugin for `doc-marshal` is a secondary feature, and not a first-class offering. 
4. Grant the engine its Claude Code permission from the plugin, not from `.claude/settings.json`. The entries `init --claude-code` writes (`Bash(doc-marshal:*)`, `Bash(uv run doc-marshal:*)`, `Bash(.venv/bin/doc-marshal:*)`) are command prefixes, so they cover only the spellings someone thought of -- an absolute path, `./.venv/bin/doc-marshal`, `python -m doc_marshal`, `poetry run doc-marshal` all still prompt, and a non-interactive session cannot answer (found in the V5 run). A PreToolUse hook in the plugin would instead parse each Bash command, strip any runner or path in front of the executable, and return `permissionDecision: allow` when the program is `doc-marshal` or `python -m doc_marshal`. Strict by construction: refuse any command containing chaining, pipes, redirection or substitution, so `doc-marshal check; rm -rf ~` is never approved the way a prefix rule would. The settings.json entries stay as the fallback for Claude Code without the plugin. Editing notes (`Edit`/`Write` under the docs root) is a separate, user-owned policy; at most `init` could print an opt-in `Edit(<docs-root>/**)` line.

5. Add a convention specifying a folder that stores images, pdfs, etc. (non-markdown) and consider adding tools like pdf extractors to this package so that these files can easily be read. Important note: the `reference` docs will frequently reference files in this folder.

6. Handle mermaid diagrams.

7. An optional `status` on `reference` and `runbook`, absent meaning `done`, for an interface still being defined or a deploy path still being built. Decided against on 2026-09-03: only `spec` carries the lifecycle for now, and a proposed reference is a spec by another name until a real tree shows otherwise.

8. Split the plugin's one general skill, `marshal-the-docs`, into several specialized skills, each for one kind of write to the tree. How to split it is deferred until the general skill has run on real trees.
