"""Chronological holdout: fit earlier months, evaluate the final complete month.
Metrics on synthetic data demonstrate the pipeline, not real banking accuracy.
"""
import gzip
import json
from pathlib import Path
import numpy as np
import joblib
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error
from ml_forecast import features,monthly_variable
ROOT=Path(__file__).resolve().parent

def train():
 manifest=json.loads((ROOT/'data/manifest.json').read_text());as_of=manifest['asOf']
 clients=[]
 with gzip.open(ROOT/'data/clients_1000.jsonl.gz','rt',encoding='utf-8') as f:
  for line in f:clients.append(json.loads(line))
 rows=[]
 for client in clients:
  series=monthly_variable(client['transactions'],as_of)
  for i in range(3,len(series)):
   rows.append((series[i][0],features([v for _,v in series[:i]],series[i][0]),series[i][1]))
 test_month=max(m for m,_,_ in rows)
 train=[r for r in rows if r[0]<test_month];test=[r for r in rows if r[0]==test_month]
 model=HistGradientBoostingRegressor(max_iter=120,max_leaf_nodes=15,l2_regularization=2,early_stopping=False,random_state=20261007)
 model.fit([r[1] for r in train],[r[2] for r in train])
 actual=np.array([r[2] for r in test]);prediction=model.predict([r[1] for r in test]);baseline=np.array([r[1][3] for r in test])
 metrics={'available':True,'model':'HistGradientBoostingRegressor','syntheticOnly':True,'clients':len(clients),'trainingRows':len(train),'validationRows':len(test),'trainingThrough':max(r[0] for r in train),'validationMonth':test_month,'maeKzt':round(mean_absolute_error(actual,prediction),2),'wapePercent':round(float(np.abs(actual-prediction).sum()/actual.sum()*100),2),'baselineMaeKzt':round(mean_absolute_error(actual,baseline),2),'forecastStrategy':'recursive monthly prediction with lag features; recurring payments added separately','annualForecastValidated':False,'sklearnVersion':__import__('sklearn').__version__}
 ROOT.joinpath('model').mkdir(exist_ok=True)
 joblib.dump(model,ROOT/'model/expenses.joblib',compress=3)
 (ROOT/'model/metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(metrics,ensure_ascii=False));return metrics
if __name__=='__main__':train()
