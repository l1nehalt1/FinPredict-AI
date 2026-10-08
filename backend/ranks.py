"""Transparent demo ranks based on budget management, not salary or subscription."""

NAMES = ['Новичок', 'Практик', 'Стратег', 'Капиталист', 'Магнат']

def complete_months(as_of, count=6):
    year, month = as_of.year, as_of.month
    result=[]
    for _ in range(count):
        month-=1
        if month==0:year-=1;month=12
        result.append(f'{year:04d}-{month:02d}')
    return list(reversed(result))

def rating(balance, monthly, as_of):
    # Only complete calendar months and recorded income/expense matter.
    keys=complete_months(as_of)
    observed=[monthly[k] for k in keys if k in monthly]
    recent=[monthly.get(k, {'income':0,'expenses':0}) for k in keys[-3:]]
    income=sum(m['income'] for m in recent)/3
    expenses=sum(m['expenses'] for m in recent)/3
    reserve=max(0,balance)/expenses if expenses>0 else 0
    saved_ratio=max(0,min(1,(income-expenses)/income)) if income>0 else 0
    positive=sum(1 for m in recent if m['income']>0 and m['income']>=m['expenses'])/3
    reserve_points=round(min(1,reserve/3)*40)
    savings_points=round(min(1,saved_ratio/.30)*35)
    stability_points=round(positive*25)
    provisional=len(observed)<3
    score=reserve_points+savings_points+stability_points
    if provisional:score=min(score,19)
    level=min(4,score//20)
    return {'score':score,'level':level,'name':NAMES[level], 'balance':balance,
        'provisional':provisional,'historyMonths':len(observed),'nextAt':(level+1)*20 if level<4 else None,
        'reserveMonths':round(reserve,2),'savingsRate':round(saved_ratio*100,1),
        'components':[{'key':'reserve','points':reserve_points,'max':40},
                      {'key':'savings','points':savings_points,'max':35},
                      {'key':'stability','points':stability_points,'max':25}]}

def from_accounts(accounts, as_of):
    balance=0;monthly={}
    for account in accounts:
        balance+=account['opening']
        for t in account['transactions']:
            if t['date']>as_of.isoformat():continue
            balance+=t['amount'] if t['type']=='income' else -t['amount']
            m=monthly.setdefault(t['date'][:7],{'income':0,'expenses':0})
            m['income' if t['type']=='income' else 'expenses']+=t['amount']
    return rating(balance,monthly,as_of)
