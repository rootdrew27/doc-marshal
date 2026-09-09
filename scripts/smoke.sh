#!/usr/bin/env bash
# End-to-end smoke test on a fresh repository: every command runs, the five-type profile validates
# what it should and rejects what it should, and the plugin's hooks resolve the installed engine.
# CI runs this on each supported Python; locally: PLUGIN=$PWD/plugin bash scripts/smoke.sh
set -eux
: "${PLUGIN:?set PLUGIN to the plugin directory}"
doc-marshal --version
doc-marshal info --types > /dev/null
doc-marshal info --marshalling > /dev/null
doc-marshal info --policies | grep -c '{{' | grep -qx 0
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
doc-marshal drifted | grep -q use-postgres
git commit -qam second
doc-marshal drifted --range HEAD~1..HEAD | grep -q use-postgres
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

# A removed import line is a doctor problem, and so is running with no docs tree at all.
sed -i.bak '/@docs\/CLAUDE.md/d' CLAUDE.md && rm CLAUDE.md.bak
! doc-marshal doctor
doc-marshal init --claude-code | grep -q '@docs/CLAUDE.md'
doc-marshal doctor
(cd "$(mktemp -d)" && ! doc-marshal doctor)

# The integration flags write the other two integrations. This engine came from a checkout,
# so `v0.3.0` is not a tag a `rev:` could resolve and init declines and says what to pass instead.
version=$(doc-marshal --version | awk '{print $2}')
doc-marshal init --pre-commit --ci | grep -q -- '--pin'
test ! -f .pre-commit-config.yaml
# The same applies to the blocks `init` prints for the ones it did not wire: a version it cannot
# vouch for is not printed as a snippet to paste either.
doc-marshal init | grep -q 'rev: vX.Y.Z'
mkdir -p .github
doc-marshal init --pre-commit --ci --pin "$version"
grep -q 'rev: v' .pre-commit-config.yaml
grep -q 'fetch-depth: 0' .github/workflows/docs.yml
grep -q 'doc-marshal==' .github/workflows/docs.yml
# A config that already names doc-marshal is left alone rather than gaining a second entry.
doc-marshal init --pre-commit --pin 0.3.0 | grep -q 'left alone'
test "$(grep -c 'rev: v' .pre-commit-config.yaml)" = 1
# doctor reads all three written jurisdictions, and a rev nothing else names is a problem.
doc-marshal doctor | grep -q '\.pre-commit-config\.yaml pins'
doc-marshal doctor | grep -q 'workflows/docs\.yml pins'
sed -i.bak 's/rev: v.*/rev: v9.9.9/' .pre-commit-config.yaml && rm .pre-commit-config.yaml.bak
! doc-marshal doctor
doc-marshal doctor | grep -q 'DOES NOT MATCH'
# upgrade moves every pin it wrote, and hands the install to the manager it does not drive.
doc-marshal upgrade "$version" --pins | grep -q 'rev: v'
doc-marshal doctor
# A second run finds every pin already at the version and says so, rather than claiming there is
# no pin to move.
doc-marshal upgrade "$version" --pins | grep -q 'already names'
# A range in the dependency table is a problem even when it admits the running version: it is the
# one jurisdiction that can move on the next resolve without anything else moving with it.
printf '[project]\nname = "x"\ndependencies = ["doc-marshal>=0.3.0"]\n' > pyproject.toml
! doc-marshal doctor
doc-marshal doctor | grep -q 'a range'
rm pyproject.toml
doc-marshal upgrade 0.4.0 --dry-run | grep -q 'would install'
doc-marshal upgrade 0.4.0 | grep -q -- '--pins'
! doc-marshal upgrade 0.4 --pins
git add -A

# The plugin's hooks resolve the installed engine and report on a broken note.
printf -- '---\ntype: decision\nstatus: bogus\nsummary: bad\n---\n# Bad\n' > docs/bad.md
export CLAUDE_PROJECT_DIR="$repo" CLAUDE_PLUGIN_ROOT="$PLUGIN"
python3 "$PLUGIN/hooks/session-start.py" | grep -q '"SessionStart"'
python3 "$PLUGIN/hooks/session-start.py" | grep -q 'Scaffold a new note'
echo "{\"tool_input\": {\"file_path\": \"$repo/docs/bad.md\"}}" | python3 "$PLUGIN/hooks/post-tool-use.py" | grep -q "ERROR: docs/bad.md"
# With no engine installed, SessionStart says so once and PostToolUse stays silent.
test -n "$(PATH=/usr/bin:/bin python3 "$PLUGIN/hooks/session-start.py")"
# It carries no install command and names no action: which version belongs here is the
# repository's decision, and an agent reads this as context at the top of an unrelated session.
PATH=/usr/bin:/bin python3 "$PLUGIN/hooks/session-start.py" | grep -q 'context, not a task'
! PATH=/usr/bin:/bin python3 "$PLUGIN/hooks/session-start.py" | grep -q 'pip install'
! PATH=/usr/bin:/bin python3 "$PLUGIN/hooks/session-start.py" | grep -q 'uv add'
test -z "$(echo "{\"tool_input\": {\"file_path\": \"$repo/docs/bad.md\"}}" | PATH=/usr/bin:/bin python3 "$PLUGIN/hooks/post-tool-use.py")"
echo "smoke: ok"
