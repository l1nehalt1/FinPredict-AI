"""Monthly variable-expense model; lag features only, no future transactions."""
import os
os.environ.setdefault("OMP_NUM_THREADS","1")
import calendar
import json
import math
from pathlib import Path
from functools import lru_cache
import joblib
ROOT=Path(__file__).resolve().parent

def next_month(month):
 y,m=map(int,month.split('-'));return f'{y+1}-01' if m==12 else f'{y}-{m+1:02d}'

def features(history,month):
 last=list(history[-6:]);n=int(month[-2:])
 return [last[-1],last[-2],last[-3],sum(last[-3:])/3,sum(last)/len(last),math.sin(2*math.pi*n/12),math.cos(2*math.pi*n/12)]

def monthly_variable(rows,as_of):
 first=min((t['date'] for t in rows),default=as_of)
 months=sorted(set(t['date'][:7] for t in rows if t['date'][:7]<as_of[:7]))
 # The first calendar month may be incomplete; exclude it in that case.
 if first[-2:]!='01':months=[m for m in months if m!=first[:7]]
 return [(m,sum(t['amount']/100 for t in rows if t['date'].startswith(m) and t['type']=='expense' and not t['recurring'])) for m in months]

@lru_cache(maxsize=1)
def load_model():
 path=ROOT/'model/expenses.joblib'
 return joblib.load(path) if path.exists() else None

def project(rows,as_of,horizon):
 model=load_model();series=monthly_variable(rows,as_of)
 if model is None or len(series)<3:return None
 values=[v for _,v in series];month=as_of[:7]
 from datetime import date,timedelta
 end=(date.fromisoformat(as_of)+timedelta(days=horizon)).isoformat()[:7]
 out={}
 while month<=end:
  raw=float(model.predict([features(values,month)])[0])
  base=max(1,sum(values[-3:])/3)
  predicted=max(base*.5,min(base*1.7,raw))
  out[month]=int(round(predicted*100));values.append(predicted)
  month=next_month(month)
 return out

def metadata():
 path=ROOT/'model/metrics.json'
 return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'available':False}

def attach(payload):
 projection=project(payload['transactions'],payload['asOf'],payload['horizon'])
 if projection:
  payload['mlMonthly']=projection
  series=monthly_variable(payload['transactions'],payload['asOf'])
  if len(series)>=4:
   actual=series[-1][1]
   estimate=float(load_model().predict([features([v for _,v in series[:-1]],series[-1][0])])[0])
   payload['mlBacktestError']=round(abs(actual-estimate)/actual*100,1) if actual else None
  payload['mlHistoryMonths']=min(6,len(series))
  payload['mlMethod']='HistGradientBoostingRegressor · лаги расходов и сезонность'
 return payload
