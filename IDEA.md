# IDEA.md

1. Consider requiring a hidden file in each directory. This hidden file could contain information analagous to what is stored in the frontmatter of each document; importantly a summary could be kept here. Additionally, this information could be used in INDEX.md or in one form of the `doc-marshal index ...` call.

2. Use an abbreviated name for imports and command line calls. This idea is worth considering as human users will be more prone to use the CLI if the commands are easier to type (e.g. `dm check --all`), but it falls out of favor if a coding agent would struggle to use the abbreviate, rather than the straight-forward and prose-structured `doc-marshal`. 