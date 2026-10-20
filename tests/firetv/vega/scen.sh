# usage: scen.sh reset | scen.sh run <stage> <branch> | scen.sh reps <n> | scen.sh state
cd "$(dirname "$0")"
case "$1" in
  reset) python3 api.py POST /api/admin/reset '{}' | cut -c1-120;;
  run) python3 api.py POST /api/admin/scenarios/$2/run "{\"branch\":\"$3\"}" | cut -c1-120;;
  reps) for i in $(seq 1 $2); do python3 api.py POST /api/admin/studio/rep '{}' | cut -c1-60; done;;
  state) OUT=/tmp/st.json python3 api.py GET /api/state >/dev/null; python3 -c "
import json;d=json.load(open('/tmp/st.json'))['state']
print([(c['key'],c['status']) for c in d['contracts']]); print([(i['incident_id'],i['status']) for i in d['incidents']]); s=d['studio'] or {}; print('studio',s.get('count'),s.get('gate'),s.get('status'),s.get('source')); print('now',d['now'],'scenario',d['scenario'])";;
esac
