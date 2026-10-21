"""Fetch a real point forecast and push it; do not pretend it is a measured grid."""
import json
from urllib.request import Request,urlopen
def main():
    url='https://api.open-meteo.com/v1/forecast?latitude=50.0755&longitude=14.4378&current=temperature_2m,wind_speed_10m&wind_speed_unit=ms'
    with urlopen(url,timeout=20) as r:weather=json.load(r)
    c=weather['current']
    payload={'type':'FeatureCollection','features':[{'type':'Feature','geometry':{'type':'Point','coordinates':[weather['longitude'],weather['latitude']]},'properties':{'name':'Open-Meteo Prague forecast','temperature':c['temperature_2m'],'unit':'°C','wind_m_s':c['wind_speed_10m'],'time':c['time']}}],'summary':{'label':'Prague forecast','value':str(c['temperature_2m'])+' °C'}}
    req=Request('http://127.0.0.1:5000/api/push/stations',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'},method='POST')
    with urlopen(req,timeout=10) as r:print(r.status,r.read().decode())
if __name__=='__main__':main()
