#!/usr/bin/env bash
# Wait for a job run to finish and print each task's result state.
RUN=$1; P=${DATABRICKS_CONFIG_PROFILE:-serverless-stable-3vku19}
while true; do
  S=$(databricks jobs get-run "$RUN" -p "$P" -o json)
  LC=$(echo "$S" | python3 -c "import sys,json; print(json.load(sys.stdin)['state']['life_cycle_state'])")
  if [[ "$LC" == "TERMINATED" || "$LC" == "INTERNAL_ERROR" || "$LC" == "SKIPPED" ]]; then break; fi
  sleep 30
done
echo "$S" | python3 -c "
import sys,json; r=json.load(sys.stdin)
print('run', r['run_id'], r['state'].get('result_state'), r['state'].get('state_message',''))
for t in r.get('tasks',[]): print(' ', t['task_key'], t['state'].get('result_state'), t.get('run_id'), round((t.get('execution_duration') or 0)/1000),'s', t['state'].get('state_message','')[:300])"
