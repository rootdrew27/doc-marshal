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

repo=$(mktemp -d)
cd "$repo"
git init -q . && git config user.email ci@example.com && git config user.name ci
printf '# Repo\n' > CLAUDE.md
doc-marshal init --claude-code
grep -qx '@docs/CLAUDE.md' CLAUDE.md
grep -q 'doc-marshal info' docs/CLAUDE.md
mkdir -p src && echo "x = 1" > src/db.py

# One note of each type the scaffolder can write without a status flag, then the sweep.
doc-marshal new decision use-postgres --code-ref src/db.py --summary "Postgres over SQLite, for concurrent writers."
doc-marshal new reference docs/vendor-limits --source https://example.com/limits --summary "Limits the vendor imposes."
doc-marshal new runbook docs/deploy --code-ref src/db.py --summary "Deploy the service."
doc-marshal new spec docs/billing --summary "How billing behaves end to end."
grep -qx 'status: proposed' docs/billing.md
test "$(cat docs/*.md docs/decisions/*.md | grep -c '## Related')" = 0
doc-marshal check --all
doc-marshal index && doc-marshal index --check
git add -A && git commit -qm init
echo "y = 2" >> src/db.py
doc-marshal affected --range HEAD | grep -q use-postgres
doc-marshal doctor

# A done spec must name its code; a removed import line is a doctor mismatch; github format annotates.
printf -- '---\ntype: spec\nupdated: 2026-09-03\nsummary: done without code\nstatus: done\n---\n# Done\n' > docs/done.md
! doc-marshal check docs/done.md
doc-marshal check docs/done.md --format github | grep -q '^::error file=docs/done.md::'
rm docs/done.md
sed -i.bak '/@docs\/CLAUDE.md/d' CLAUDE.md && rm CLAUDE.md.bak
! doc-marshal doctor
doc-marshal init --claude-code | grep -q '@docs/CLAUDE.md'
doc-marshal doctor

# The plugin's hooks resolve the installed engine and report on a broken note.
printf -- '---\ntype: decision\nstatus: bogus\nsummary: bad\n---\n# Bad\n' > docs/bad.md
export CLAUDE_PROJECT_DIR="$repo" CLAUDE_PLUGIN_ROOT="$PLUGIN"
python3 "$PLUGIN/hooks/session-start.py" | grep -q '"SessionStart"'
echo "{\"tool_input\": {\"file_path\": \"$repo/docs/bad.md\"}}" | python3 "$PLUGIN/hooks/post-tool-use.py" | grep -q "ERROR: docs/bad.md"
# With no engine installed, SessionStart says so once and PostToolUse stays silent.
test -n "$(PATH=/usr/bin:/bin python3 "$PLUGIN/hooks/session-start.py")"
test -z "$(echo "{\"tool_input\": {\"file_path\": \"$repo/docs/bad.md\"}}" | PATH=/usr/bin:/bin python3 "$PLUGIN/hooks/post-tool-use.py")"
echo "smoke: ok"
