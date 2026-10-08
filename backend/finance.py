"""Financial calculations shared by the hosted MicroPython runtime and CPython API.
Amounts are integer tiyn. This is an interpretable demo forecast, not a trained model.
"""
import json
import math
import calendar

def totals(rows):
    income=sum(t['amount'] for t in rows if t['type']=='income')
    expenses=sum(t['amount'] for t in rows if t['type']=='expense')
    return income,expenses

def change(current,previous):
    return round((current-previous)/previous*100,1) if previous else None

def dashboard(data):
    rows=data['transactions']
    months=sorted(set(t['date'][:7] for t in rows))
    period=data.get('period') or months[-1]
    selected=[t for t in rows if t['date'].startswith(period)]
    monthly=[]
    for month in months:
        income,expenses=totals([t for t in rows if t['date'].startswith(month)])
        monthly.append({'month':month,'income':income,'expenses':expenses,'net':income-expenses})
    income,expenses=totals(selected)
    previous=data.get('previousPeriod','')
    pi,pe=totals([t for t in rows if t['date'].startswith(previous)])
    all_income,all_expenses=totals(rows)
    cats={}
    for t in selected:
        if t['type']=='expense':cats[t['category']]=cats.get(t['category'],0)+t['amount']
    category_totals=[{'category':c,'amount':v,'share':round(v/expenses*100,1) if expenses else 0} for c,v in cats.items()]
    category_totals.sort(key=lambda c:c['amount'],reverse=True)
    days=[]
    cumulative=0
    for date in data['days']:
        di,de=totals([t for t in selected if t['date']==date])
        cumulative+=de
        days.append({'date':date,'income':di,'expenses':de,'cumulative':cumulative})
    return {'transactions':rows,'months':months,'period':period,'asOf':data['asOf'],'historyStart':data.get('historyStart'),'account':data['account'],
      'summary':{'balance':data['account']['opening']+all_income-all_expenses,'income':income,'expenses':expenses,'net':income-expenses,'incomeChange':change(income,pi),'expenseChange':change(expenses,pe),'savingsRate':round((income-expenses)/income*100,1) if income else 0,'count':len(selected)},
      'monthly':monthly,'daily':days,'categoryTotals':category_totals}

def forecast(data):
    rows=data['transactions']
    as_of=data['asOf']
    full_months=sorted(set(t['date'][:7] for t in rows if t['date'][:7]<as_of[:7]))
    history=full_months[-3:]
    horizon=data['horizon']
    scenario=data.get('scenario','base')
    savings=data.get('savings',0)
    monthly=[]
    cat_values={}
    for month in history:
        expenses=[t for t in rows if t['type']=='expense' and not t['recurring'] and t['date'].startswith(month)]
        monthly.append(sum(t['amount'] for t in expenses))
        for t in expenses:
            cat_values.setdefault(t['category'],{}).setdefault(month,0)
            cat_values[t['category']][month]+=t['amount']
    weights=([0.2,0.3,0.5][-len(history):]) if history else []
    weight_sum=sum(weights) or 1
    weighted=sum(v*w for v,w in zip(monthly,weights))/weight_sum
    trend=max(-0.15,min(0.15,(monthly[-1]-monthly[0])/max(1,monthly[0])/max(1,len(monthly)-1))) if len(monthly)>1 else 0
    factor={'base':1,'high':1.10,'low':0.90}[scenario]
    daily_base=weighted/30.44*(1+trend)*factor
    recurring={}
    for t in sorted(rows,key=lambda t:t['date']):
        if t['recurring'] and t['date'][:7] in history:
            recurring[(t['description'],t['type'])]=t
    cat_daily={}
    for cat,values in cat_values.items():
        v=sum(values.get(m,0)*w for m,w in zip(history,weights))/weight_sum/30.44*(1+trend)*factor
        cat_daily[cat]=v
    discretionary=set(['cafe','shopping','leisure'])
    reductions=sum(v*savings/100 for cat,v in cat_daily.items() if cat in discretionary)
    # Forward-only backtest: predict September from June-August, no future leakage.
    backtest_error=None
    if len(full_months)>=4:
        training=full_months[-4:-1]
        actual=totals([t for t in rows if t['date'].startswith(full_months[-1])])[1]
        predicted=sum(totals([t for t in rows if t['date'].startswith(m)])[1]*w for m,w in zip(training,[0.2,0.3,0.5]))
        backtest_error=round(abs(actual-predicted)/actual*100,1) if actual else None
    backtest_error=data.get('mlBacktestError',backtest_error)
    spread=max(0.15,min(0.35,(backtest_error or 15)/100*2))
    spread=min(.75,spread*math.sqrt(max(1,horizon/30)))
    ai,ae=totals(rows)
    balance=data['account']['opening']+ai-ae
    current_balance=balance
    total=0
    baseline=0
    income_total=0
    cats={c:0 for c in cat_daily}
    days=[]
    for index,date in enumerate(data['futureDays']):
        day=int(date[-2:])
        month_days=calendar.monthrange(int(date[:4]),int(date[5:7]))[1]
        predicted_month=data.get('mlMonthly',{}).get(date[:7])
        scale=(predicted_month/month_days*factor/daily_base) if predicted_month is not None and daily_base>0 else 1
        multiplier=1+(0.06 if (index%7 in [4,5]) else -0.024)
        expense=int(round((daily_base-reductions)*scale*multiplier))
        base=int(round(daily_base*scale*multiplier))
        income=0
        for cat,value in cat_daily.items():
            cats[cat]+=value*scale*multiplier*(1-savings/100 if cat in discretionary else 1)
        for t in recurring.values():
            if min(int(t['date'][-2:]),month_days)==day:
                if t['type']=='expense':
                    expense+=t['amount'];base+=t['amount'];cats[t['category']]=cats.get(t['category'],0)+t['amount']
                else:income+=t['amount']
        total+=expense;baseline+=base;income_total+=income;balance+=income-expense
        days.append({'date':date,'expenses':expense,'cumulative':total,'low':int(total*(1-spread)),'high':int(total*(1+spread)),'balance':balance,'income':income})
    category_result=[{'category':c,'amount':int(round(v)),'share':round(v/total*100,1) if total else 0} for c,v in cats.items()]
    category_result.sort(key=lambda t:t['amount'],reverse=True)
    return {'horizon':horizon,'scenario':scenario,'savings':savings,'total':total,'low':int(total*(1-spread)),'high':int(total*(1+spread)),
      'expectedIncome':income_total,'currentBalance':current_balance,'endBalance':balance,'daily':days,'categories':category_result,'baseline':baseline,'saved':baseline-total,
      'backtestError':backtest_error,'historyMonths':data.get('mlHistoryMonths',len(history)),'method':data.get('mlMethod','Взвешенное среднее за 3 месяца + тренд + регулярные платежи'),
      'periodStart':data['futureDays'][0],'periodEnd':data['futureDays'][-1]}

def run_json(payload):
    data=json.loads(payload)
    result=forecast(data) if data.get('action')=='forecast' else dashboard(data)
    return json.dumps(result)
