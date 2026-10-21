"""Push synthetic observations via REST, at any cadence."""
import argparse,json,sys,time
from pathlib import Path
from urllib.request import Request,urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from providers import snapshot,CENTERS
def main():
    p=argparse.ArgumentParser()
    p.add_argument('--server',default='http://127.0.0.1:5000')
    p.add_argument('--location',choices=CENTERS,default='prague')
    p.add_argument('--interval',type=float,default=5)
    args=p.parse_args()
    if args.interval<=0:p.error('interval must be positive')
    while True:
        for kind in ('temperature','pressure','wind','stations'):
            req=Request(args.server+'/api/push/'+kind+'?location='+args.location,data=json.dumps(snapshot(kind,args.location)).encode(),headers={'Content-Type':'application/json'},method='POST')
            with urlopen(req,timeout=10) as r:print(kind,r.status)
        time.sleep(args.interval)
if __name__=='__main__':main()
