import json
import sys
from pathlib import Path
from datetime import date,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from finance import dashboard,forecast
seed=json.loads((Path(__file__).resolve().parents[1]/'backend/demo-data.json').read_text())
rows=seed['transactions']
d=dashboard({**seed,'period':'2026-09','previousPeriod':'2026-08','days':['2026-09-%02d'%i for i in range(1,31)]})
assert d['summary']['expenses']==d['daily'][-1]['cumulative']
assert d['summary']['balance']==seed['account']['opening']+sum(t['amount']*(1 if t['type']=='income' else -1) for t in rows)
assert sum(c['amount'] for c in d['categoryTotals'])==d['summary']['expenses']
start=date.fromisoformat(seed['asOf'])
params={**seed,'horizon':30,'scenario':'base','savings':0,'futureDays':[(start+timedelta(days=i)).isoformat() for i in range(1,31)]}
f=forecast(params)
assert f['daily'][-1]['cumulative']==f['total']
assert f['endBalance']==f['currentBalance']+f['expectedIncome']-f['total']
assert f['low']<f['total']<f['high']
assert forecast({**params,'savings':30})['total']<f['total']
assert forecast({**params,'scenario':'high'})['total']>f['total']
assert forecast({**params,'scenario':'low'})['total']<f['total']
assert abs(sum(c['amount'] for c in f['categories'])-f['total'])<100
assert len(rows)>400
print('CPython finance invariants passed')
from ml_forecast import attach
for horizon in (30,60,90,180,365):
    payload={**seed,'horizon':horizon,'scenario':'base','savings':0,'futureDays':[(start+timedelta(days=i)).isoformat() for i in range(1,horizon+1)]}
    prediction=forecast(attach(payload))
    assert len(prediction['daily'])==horizon
    assert prediction['daily'][-1]['cumulative']==prediction['total']
    assert prediction['endBalance']==prediction['currentBalance']+prediction['expectedIncome']-prediction['total']
    assert abs(sum(c['amount'] for c in prediction['categories'])-prediction['total'])<1000
    assert forecast(attach({**payload,'savings':30}))['total']<prediction['total']
    assert prediction['periodStart']>'2026-10-07'
print('ML forecasts passed for 30/60/90/180/365 days; balances, categories and scenarios are consistent')
