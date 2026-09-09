`docs/` is a doc-marshal docs tree: typed markdown notes whose primary reader is a coding
agent. The policies ship in the tool, not in this file.

```bash
doc-marshal info                 # the note types and their anchors, one line each
doc-marshal info <type>          # one type in full: what it serves, how it reads, its template
doc-marshal info --policies      # every policy for this tree
doc-marshal info --marshalling   # how these docs are written: for a change, a subject, or a clean-up
doc-marshal check <path>         # validates a note against the policies; --all sweeps the tree
doc-marshal new <type> <path>    # scaffolds a note with the frontmatter and sections its type requires
doc-marshal drifted              # the notes anchored to code a change touched
doc-marshal index                # regenerates INDEX.md
```

- `INDEX.md` -- generated routing surface: one line per note with its type and summary.
- `NOMENCLATURE.md` -- the shared vocabulary for docs and code, and the aliases it rules out.
