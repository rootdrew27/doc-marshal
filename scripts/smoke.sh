#!/usr/bin/env bash
# End-to-end smoke test on a fresh repository: every command runs, the five-type preset validates
# what it should and rejects what it should, and the plugin's hooks resolve the installed engine.
# CI runs this on each supported Python; locally: PLUGIN=$PWD/plugin bash scripts/smoke.sh
set -eux
: "${PLUGIN:?set PLUGIN to the plugin directory}"
doc-marshal --version
doc-marshal info --types > /dev/null
doc-marshal info --process > /dev/null
doc-marshal info --conventions | grep -c '{{' | grep -qx 0
test "$(doc-marshal info --types | grep -c '^## `')" = 5
doc-marshal info spec | grep -q 'required, in this order'

repo=$(mktemp -d)
cd "$repo"
git init -q . && git config user.email ci@example.com && git config user.name ci
printf '# Repo\n' > CLAUDE.md
doc-marshal init --claude-code
grep -qx '@docs/CLAUDE.md' CLAUDE.md
grep -q 'doc-marshal info' docs/CLAUDE.md
mkdir -p src && echo "x = 1" > src/db.py

# One note of each type the scaffolder can write without a status flag. A scaffold does not pass
# until its required sections are written and its anchors are tracked, and says so.
doc-marshal new decision use-postgres --code-ref src/db.py --summary "Postgres over SQLite, for concurrent writers."
doc-marshal new reference docs/vendor-limits --source https://example.com/limits --summary "Limits the vendor imposes."
doc-marshal new runbook docs/deploy --code-ref src/db.py --summary "Deploy the service."
doc-marshal new spec docs/billing --summary "How billing behaves end to end."
grep -qx 'status: proposed' docs/billing.md
grep -qx '## Prerequisites' docs/deploy.md && grep -qx '## Open questions' docs/billing.md
! doc-marshal check docs/deploy.md
doc-marshal check docs/deploy.md | grep -q 'is empty'
doc-marshal check docs/deploy.md | grep -q 'does not track'
! doc-marshal new decision born-dead --status superseded --summary "A note is never born superseded."
for note in docs/deploy.md docs/billing.md docs/decisions/0001-use-postgres.md; do
  python3 - "$note" <<'EOF'
import re, sys
path = sys.argv[1]
text = open(path).read()
open(path, "w").write(re.sub(r"(## [^\n]+\n)\n<!--.*?-->", lambda m: m.group(1) + "\nOne true line.", text, flags=re.S))
EOF
done
git add -A
doc-marshal check --all
doc-marshal index && doc-marshal index --check
git add -A && git commit -qm init
echo "y = 2" >> src/db.py
doc-marshal affected | grep -q use-postgres
git commit -qam second
doc-marshal affected --range HEAD~1..HEAD | grep -q use-postgres
! doc-marshal check --all --range HEAD           # not A..B
! doc-marshal check --all --range HEAD~1...HEAD  # three dots
doc-marshal doctor

# Shape: a done spec must name its code and hold no open question; a title is one H1 with the
# number its filename carries; an unknown frontmatter key is an error; github format annotates.
printf -- '---\ntype: spec\nupdated: 2026-09-03\nsummary: done without code\nstatus: done\n---\n# Done\n' > docs/done.md
! doc-marshal check docs/done.md
doc-marshal check docs/done.md --format github | grep -q '^::error file=docs/done.md::'
rm docs/done.md
sed 's/^# 0001 -- /# /' docs/decisions/0001-use-postgres.md > docs/decisions/0002-untitled.md
doc-marshal check docs/decisions/0002-untitled.md | grep -q 'starts with its number'
rm docs/decisions/0002-untitled.md
printf -- '---\ntype: reference\nupdated: 2026-09-03\nsummary: t\nsource:\n  - https://x.example\ncode-refs:\n  - src/db.py\n---\n# T\n\ntext\n' > docs/typo.md
doc-marshal check docs/typo.md | grep -q "unknown frontmatter key 'code-refs'"
rm docs/typo.md
mkdir -p docs/sub && printf 'x\n' > docs/sub/INDEX.md && printf 'x\n' > docs/Readme.md
doc-marshal check --all | grep -c 'does not belong' | grep -qx 2
rm -r docs/sub docs/Readme.md

# A removed import line is a doctor problem, and so is running with no docs root at all.
sed -i.bak '/@docs\/CLAUDE.md/d' CLAUDE.md && rm CLAUDE.md.bak
! doc-marshal doctor
doc-marshal init --claude-code | grep -q '@docs/CLAUDE.md'
doc-marshal doctor
(cd "$(mktemp -d)" && ! doc-marshal doctor)

# The plugin's hooks resolve the installed engine and report on a broken note.
printf -- '---\ntype: decision\nstatus: bogus\nsummary: bad\n---\n# Bad\n' > docs/bad.md
export CLAUDE_PROJECT_DIR="$repo" CLAUDE_PLUGIN_ROOT="$PLUGIN"
python3 "$PLUGIN/hooks/session-start.py" | grep -q '"SessionStart"'
python3 "$PLUGIN/hooks/session-start.py" | grep -q 'Scaffold a new note'
echo "{\"tool_input\": {\"file_path\": \"$repo/docs/bad.md\"}}" | python3 "$PLUGIN/hooks/post-tool-use.py" | grep -q "ERROR: docs/bad.md"
# With no engine installed, SessionStart says so once and PostToolUse stays silent.
test -n "$(PATH=/usr/bin:/bin python3 "$PLUGIN/hooks/session-start.py")"
test -z "$(echo "{\"tool_input\": {\"file_path\": \"$repo/docs/bad.md\"}}" | PATH=/usr/bin:/bin python3 "$PLUGIN/hooks/post-tool-use.py")"
echo "smoke: ok"
