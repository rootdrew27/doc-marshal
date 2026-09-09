---
type: reference
updated: 2026-09-08
summary: "What the policies do not see: the limits of the naming, frontmatter, links, numbering, alias and vocabulary checks"
code_refs:
  - src/doc_marshal/policies.py
  - src/doc_marshal/markdown.py
  - src/doc_marshal/frontmatter.py
  - src/doc_marshal/vocabulary.py
---

# What the policies do not see

Recorded so that nobody reads a clean `check` as covering these. Each one is a deliberate choice or
a limit of a subset parser, not a gap waiting to be discovered. `doc-marshal info --policies`
states what *is* checked; this note is its complement.

## Names

- The kebab-case pattern is ASCII only, so an accented filename fails.
- A name may begin with a digit.
- A dotfile fails the naming policy unless it is one of the non-notes `doc-marshal info --policies`
  lists, which are never validated or indexed.
- An agent-memory file is never a note anywhere under the tree, so a nested `CLAUDE.md`, or both
  `CLAUDE.md` and `AGENTS.md` at the top of the tree, pass without comment.

## Frontmatter

- The parser reads scalars and dash-item lists and nothing richer.
- The block must open at the first byte of the file. A UTF-8 byte-order mark, or a blank line
  before the opening `---`, reads as no frontmatter at all.
- A nested mapping or a stray indented line is reported as unparseable frontmatter, not as the
  specific thing it was.
- A flow list, `key: [a, b]`, is read as a scalar string. Where the field is an anchor, the error
  reported is that it is not a list.
- A quoted value is unescaped for `\"` and `\\` only, and a single-quoted `''` is not unescaped
  at all, so any other escape a hand-written value carries reaches the generated index verbatim.
- `https://` with nothing after it passes as a URL.

## Links

- A `?query` suffix is part of the path as read, so such a target is reported as broken.
- An HTML `<a href>` and a reference-style definition, `[r]: x.md`, are not checked at all.
- A target with a URL scheme, and anything inside a code span or a fenced block, is not checked.

## Numbering

`new` derives the next number from the working tree, so two worktrees or two branches can hand out
the same one. The collision surfaces on merge as the uniqueness error, and the later note is
renumbered then.

## Which notes a change reaches

`drifted` answers from the anchors and nothing else, so a note whose subject a change falsified
*without* touching a path it names does not appear. Its output is a starting set in both
directions: a note that does appear may describe a part of the code the change never reached.

## The alias scan

- An indented code block is not a fence, so it is scanned.
- A multi-word alias is followed across a single line break inside a paragraph, never across a
  paragraph break.
- The scan is a whole-word match and cannot see intent, which is why it warns rather than errors.

## Nomenclature notes

- A second table under `## Terminology` is read as more rows of the first.
- A `###` heading inside a section is ordinary content; only `##` starts a section.
- The type reserves its filename but not its location, so a `NOMENCLATURE.md` under `decisions/` is
  accepted as the vocabulary of that subtree.

## Enforcement

- `--format github` annotates the file, not a line: the validator reports on notes, not positions.
- `append_only` is a property `info` renders and the alias scan reads, and nothing else. That a
  `decision` is never edited after acceptance is a convention the tool does not hold.
- Only the docs tree is scanned against the vocabulary. Whether the code uses the same terms is a
  review obligation.
