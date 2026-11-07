#!/usr/bin/env bash
# Capture deployed-app status + headless functional test output into evidence/10_app_smoke_test.md
set -euo pipefail
P=${DATABRICKS_CONFIG_PROFILE:-serverless-stable-3vku19}
URL=$(databricks apps get inventory-risk-radar -p "$P" -o json | python3 -c "import sys,json; print(json.load(sys.stdin)['url'])")
OUT=$(DATABRICKS_CONFIG_PROFILE=$P GENIE_SPACE_ID=$GENIE_SPACE_ID uv run -q --with-requirements src/app/requirements.txt --with pytest \
      pytest -q tests/test_app_smoke.py -s -p no:warnings 2>&1 | grep -v "ScriptRunContext")
TOK=$(databricks auth token -p "$P" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
H=$(curl -s -w " HTTP %{http_code}" -H "Authorization: Bearer $TOK" "$URL/_stcore/health")
LOGS=$(databricks apps logs inventory-risk-radar -p "$P" --tail-lines 15 2>&1 | grep -v aitools)
cat > evidence/10_app_smoke_test.md <<EOF
# Planner app: deployed status and headless functional test

_Captured $(date -u +"%Y-%m-%d %H:%M UTC")._

## Deployed app

- App: \`inventory-risk-radar\` (bundle resource \`planner_app\`), URL $URL
- Health endpoint with workspace OAuth: \`${H}\`

### App log excerpt (\`databricks apps logs\`)

\`\`\`text
${LOGS}
\`\`\`

## Headless functional test (\`tests/test_app_smoke.py\`)

Runs \`src/app/app.py\` with Streamlit \`AppTest\` against the real Lakebase database, SQL warehouse and Genie space. It checks that the KPIs render, the 4 tabs exist, a planner decision, note and watchlist entry round-trip through Lakebase, the 28-day drill-down returns from Delta, and Genie answers with SQL.

\`\`\`text
${OUT}
\`\`\`
EOF
echo "wrote evidence/10_app_smoke_test.md"
