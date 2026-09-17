---
type: reference
updated: 2026-09-16
summary: "What Claude Code guarantees the plugin builds on: hook events and their output, the worktree path split, why the Bash permission entries cannot be completed, and the skill listing budget"
code_refs:
  - plugin
  - src/doc_marshal/init.py
source:
  - https://code.claude.com/docs/en/hooks
  - https://code.claude.com/docs/en/permissions
  - https://code.claude.com/docs/en/skills
---

# The Claude Code harness

Facts about Claude Code, not about this engine: the behaviour the plugin and `init --claude-code`
are built on. They are the harness's to change, and it changes them often, so every claim here was
read from the three cited sources on 2026-09-16 and carries no guarantee past that date. The
anchors are URLs to versionless addresses, so nothing in this repository detects it when one of
them stops being true. What this engine does with these facts is [integrations](integrations.md).

## Hook events

Claude Code defines 33 hook events. The plugin registers two, in `plugin/hooks/hooks.json`:
`SessionStart` and `PostToolUse`. The rest exist and are unused.

The events that bear on work this repository has considered:

| Event | When it fires |
| --- | --- |
| `PermissionRequest` | when a tool call needs a permission decision |
| `FileChanged` | when a watched file changes on disk; the `matcher` field selects the filenames watched |
| `InstructionsLoaded` | when a `CLAUDE.md` or `.claude/rules/*.md` file is loaded into context, at session start and on later lazy loads |
| `PostToolUseFailure` | after a tool call fails |
| `PreCompact`, `PostCompact` | before and after context compaction |

A hook entry declares one of five handler types: `command` runs a shell command and reads the
event's JSON on stdin, `http` posts that JSON to a URL, `mcp_tool` calls a tool on a connected MCP
server, `prompt` sends a single-turn evaluation to a model, and `agent` spawns a subagent. Both of
the plugin's hooks are `command`, which is the only type that runs without a network call or a
model call.

## Where a hook's output goes

Stdout reaches the session for four events only: `UserPromptSubmit`, `UserPromptExpansion`,
`SessionStart` and `PostModelSwitch`. For every other event Claude Code writes stdout to the debug
log and does not show it. `PostToolUse` is one of the silent ones, so a `PostToolUse` hook that
prints its result plainly has printed it nowhere the agent will read.

Both plugin hooks emit a JSON object carrying `hookSpecificOutput.additionalContext`, which is what
puts their output in front of the agent. `PostToolUse` cannot block: the tool has already run, and
exit code 2 only shows stderr.

## Two roots in a worktree

`CLAUDE_PROJECT_DIR` and the `cwd` field of a hook's input JSON answer different questions, and
they diverge exactly when a session enters a worktree:

| | What it names after Claude enters a worktree |
| --- | --- |
| `CLAUDE_PROJECT_DIR` | stays at the project root where the session started -- the main checkout |
| `cwd` | the worktree root, and the new directory after Claude runs `cd` |

The environment variable is the stable address of a hook's own files, which is why
`${CLAUDE_PLUGIN_ROOT}` and `${CLAUDE_PROJECT_DIR}` are the right way to reach a script. It is the
wrong address for the tree the agent is editing. A hook that must know which directory Claude is
working in reads `cwd`.

Claude Code exports `CLAUDE_PLUGIN_ROOT`, `CLAUDE_PLUGIN_DATA` and `CLAUDE_PROJECT_DIR` to hook
subprocesses as environment variables, which is why they arrive even though the plugin's hooks run
with `PATH` stripped to `/usr/bin:/bin`.

## Why the Bash permission entries cannot be completed

Before matching a Bash entry in `permissions.allow`, Claude Code strips a fixed set of wrappers:
`timeout`, `time`, `nice`, `nohup`, `stdbuf`, the shell builtins `command` and `builtin`, and zsh's
`noglob`. Bare `xargs` is stripped too, but only with no flags -- `xargs -n1 grep` is matched as an
`xargs` command. The query form `command -v` and zsh's `nocorrect` are not stripped. A leading
assignment of certain known-safe environment variables is stripped separately, so `Bash(npm test *)`
matches `NODE_ENV=test npm test`.

**That wrapper list is built in and is not configurable, and development environment runners are
not in it** -- Claude Code names `direnv exec`, `devbox run`, `mise exec`, `npx` and `docker exec`.
Its stated remedy is to write one entry per runner and inner command together, such as
`Bash(devbox run npm test)`, and to add one entry per inner command allowed.

Two consequences for the three entries `init --claude-code` writes:

- `Bash(uv run doc-marshal:*)` is exactly the prescribed runner-plus-inner-command shape. It is
  correct, and it is also the reason the set is open-ended: every further runner a repository uses
  -- `poetry run`, `pixi run`, `hatch run`, a bare absolute path, `python -m doc_marshal` -- needs
  its own entry, and no entry generalises to the next one.
- Exec wrappers such as `watch`, `setsid`, `ionice` and `flock` cannot be auto-approved by a prefix
  entry at all, and always ask in Manual mode -- the `default` permission mode, which prompts on
  first use of each tool.

Enumerating harder does not close this. Only a hook sees the command text before the decision.

## What a hook may do to a permission decision

Two events reach a permission decision, and they are not the same event. `PreToolUse` fires
before *every* tool call executes, ahead of the permission prompt, for every tool except
`EndConversation`; its output can deny the call, force a prompt, or skip the prompt and let the
call proceed. `PermissionRequest` fires only when a call actually needs a permission decision --
so it does not run for a call already settled by the configured entries. Which of the two suits an
affirmative allow for this engine is an open question here, not a settled one; both are listed
because the choice has not been made.

The limit that makes this safe to build on: **hook decisions do not override the configured
entries.** Claude Code evaluates `deny` and `ask` regardless of what a `PreToolUse` hook returns --
a matching `deny` blocks the call, and a matching `ask` still prompts even when the hook returned
`allow`. Managed settings are included. The precedence runs the other way for blocking: a hook
exiting with code 2 stops the call before the configured entries are evaluated at all, so it
overrides an `allow`.

An affirmative-only hook therefore cannot widen what a repository already forbids, while a
denying hook can narrow it.

## Skills

- Claude Code loads a listing of every skill name into context, with descriptions. The listing's
  character budget **scales at 1% of the model's context window**, adjustable with the
  `skillListingBudgetFraction` setting. When the listing overflows, Claude Code shortens
  descriptions, dropping them starting with the skills invoked least, so a long description on a
  rarely-used skill is the first thing lost. `/doctor` estimates the cost and its largest
  contributors.
- Descriptions are loaded at startup; full skill content loads only when the skill is invoked. A
  subagent with preloaded skills differs -- there the full content is injected at startup.
- Once invoked, the rendered `SKILL.md` enters the conversation as one message and stays across
  later turns. **Claude Code does not re-read the file on later turns**, so anything that must hold
  for the whole task belongs there as a standing instruction rather than as a first step.
- Claude Code's skills doc sets a ceiling of 500 lines for a `SKILL.md` body, with detailed material moved to separate
  files. A skill's body loads only when used, so material behind it costs almost nothing until it
  is needed -- unlike `CLAUDE.md` content, which is loaded whether or not it is wanted.

`plugin/skills/marshal-the-docs/SKILL.md` is 24 lines with a 684-character description. The body is
far inside the ceiling; the description is the part that competes for the shared listing budget.

## Memory files

An `@path` import in `CLAUDE.md` is expanded and loaded at launch, alongside the file that names
it. Splitting a file into imports organises it and does not reduce what is loaded. A nested
`CLAUDE.md` under a subdirectory is different: it is loaded when Claude reads files in that
subdirectory, not at launch. The import line `init --claude-code` writes is therefore the eager
choice, taken deliberately -- see [integrations](integrations.md) for why the docs-tree pointer has
to arrive before a session opens the tree.
