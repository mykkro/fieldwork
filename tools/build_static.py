"""Refresh portable synthetic demo snapshots."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from providers import CENTERS,snapshot
for location in CENTERS:
    target=ROOT/'static'/'demo'/location
    target.mkdir(parents=True,exist_ok=True)
    for kind in ('temperature','pressure','wind','dem','stations','route'):
        (target/(kind+'.json')).write_text(json.dumps(snapshot(kind,location,tick=0),ensure_ascii=False),encoding='utf-8')
print('Static snapshots ready')
