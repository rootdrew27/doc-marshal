# doc-marshal

A machine-checked documentation tree for repositories whose primary reader is a coding agent.

> **Status: pre-alpha, unbuilt.** The design is settled and written down in
> [SPEC.md](SPEC.md). This release exists to reserve the name.

Documentation rots because nothing connects a document to the thing that would falsify it.
`doc-marshal` makes that connection mechanical: every living note declares, in frontmatter, the
code or sources it describes, so "which docs did this change invalidate?" is a question with an
answer a script can give.

It ships an opinionated eight-type ontology -- but the engine is the product, and an ontology you
declare yourself is held to exactly the same standard.

## What it will do

```bash
doc-marshal check --all        # validate every note against the ontology
doc-marshal index              # regenerate the one generated index
doc-marshal affected           # notes whose anchors name code this change touched
doc-marshal new decision ...   # scaffold a note the validator accepts
doc-marshal info               # the effective ruleset, for a human or an agent
doc-marshal init               # wire it into a repository
```

Enforcement runs at four points -- as an agent writes a note, at `git commit` via pre-commit, and
twice in CI -- so an error surfaces at the earliest point that can see it.

## License

MIT.
