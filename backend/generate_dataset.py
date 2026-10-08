"""Deterministic synthetic clients, annual past transactions; no real bank data."""
import calendar
import gzip
import json
import math
import random
import uuid
from datetime import date,timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parent
AS_OF=date(2026,10,7)
START=AS_OF-timedelta(days=364)
NAMESPACE=uuid.UUID('751dddb5-659a-4824-978a-0fe7cff74620')
FIRST=['Ерасыл','Алишер','Ернұр','Мади','Бекарыс','Данияр','Арман','Әли','Нұрсұлтан','Айдос','Айдана','Аружан','Дана','Әсел','Мадина','Алина','Жанель','Аяулым','Назерке','Диана']
LAST=['Сұлтанов','Әбілов','Омаров','Қасымов','Ахметов','Төлегенов','Нұрланов','Серікбаев','Әлиев','Бекенов','Сағындықов','Мұратов','Ибраев','Жұмабаев','Есенов','Тұрсынов','Рахимов','Қайратов','Маратұлы','Еркінов']
CITY=['Астана','Алматы','Шымкент','Қарағанды','Ақтөбе','Атырау','Қызылорда','Тараз','Павлодар','Өскемен']
JOBS=['Студент','Разработчик','Учитель','Врач','Менеджер','Инженер','Предприниматель','Дизайнер','Бухгалтер','Пенсионер']
SEGMENTS=['student','standard','family','premium']
NAMES={'housing':'Аренда квартиры','food':'Magnum · продукты','cafe':'Coffee Boom','shopping':'Ozon · покупки','transport':'Яндекс Go','services':'Мобильная связь','health':'Аптека · Europharma','leisure':'Kinopark · кино','salary':'Зарплата · Tech Solutions','freelance':'Разработка Python · проект'}

def generate_client(index):
 r=random.Random(20261007+index*7919)
 key=f'demo{index:04d}'
 uid=str(uuid.uuid5(NAMESPACE,key));aid=str(uuid.uuid5(NAMESPACE,key+':account'))
 segment=SEGMENTS[index%4]
 age=r.randint(18,25) if segment=='student' else r.randint(26,65)
 income=r.randint(150,300)*1000 if segment=='student' else r.randint(300,1200)*1000
 name=f'{r.choice(LAST)} {r.choice(FIRST)}'
 profile={'id':uid,'accountId':aid,'sourceId':key,'name':name,'email':f'client{index:04d}@example.test','city':r.choice(CITY),'age':age,'occupation':r.choice(JOBS),'segment':segment,'monthlyIncome':income*100,'opening':r.randint(300,1500)*100000,'number':f'DEMO {index:04d} {r.randrange(10000):04d}'}
 propensity=r.uniform(.35,.75);rent=income*r.uniform(.10,.25)
 if segment=='student':profile['occupation']='Студент'
 if age>=62:profile['occupation']='Пенсионер'
 if segment!='student' and age<62 and profile['occupation'] in ['Студент','Пенсионер']:profile['occupation']='Менеджер'
 tx=[];month=date(START.year,START.month,1)
 def add(d,cat,amount,kind='expense',recurring=False,description=None):
  if not START<=d<=AS_OF:return
  identifier=str(uuid.uuid5(NAMESPACE,f'{key}:{len(tx)}:{d}'))
  tx.append({'id':identifier,'date':d.isoformat(),'description':description or NAMES[cat],'category':cat,'type':kind,'amount':max(100,int(round(amount*100))),'recurring':int(recurring)})
 while month<=AS_OF:
  maxday=calendar.monthrange(month.year,month.month)[1]
  drift=1+((month.year-START.year)*12+month.month-START.month)*r.uniform(-.003,.009)
  add(month.replace(day=5),'salary',income*drift,'income',True)
  add(month.replace(day=10),'housing',rent,recurring=True)
  add(month.replace(day=15),'services',r.randint(4000,7000),recurring=True)
  add(month.replace(day=18),'services',r.randint(8000,18000),recurring=True,description='Коммунальные услуги')
  if segment=='premium':add(month.replace(day=20),'freelance',income*.18,'income',True)
  season=1+.12*math.sin(2*math.pi*(month.month-2)/12)
  variable=income*propensity*season*drift*r.uniform(.91,1.09)
  for cat,share,count in [('food',.33,12),('transport',.11,7),('cafe',.13,5),('shopping',.23,3),('health',.06,1),('leisure',.14,3)]:
   amounts=[r.uniform(.65,1.35) for _ in range(count)];scale=variable*share/sum(amounts)
   for value in amounts:add(month.replace(day=r.randint(1,maxday)),cat,value*scale)
  month=date(month.year+1,1,1) if month.month==12 else date(month.year,month.month+1,1)
 profile['transactions']=sorted(tx,key=lambda t:(t['date'],t['id']))
 return profile

def generate(count=1000):
 output=ROOT/'data/clients_1000.jsonl.gz';output.parent.mkdir(exist_ok=True)
 transactions=0;expense=0
 with gzip.open(output,'wt',encoding='utf-8',compresslevel=6) as stream:
  for i in range(1,count+1):
   client=generate_client(i);transactions+=len(client['transactions']);expense+=sum(t['amount'] for t in client['transactions'] if t['type']=='expense')
   stream.write(json.dumps(client,ensure_ascii=False,separators=(',',':'))+'\n')
 report={'synthetic':True,'clients':count,'transactions':transactions,'historyStart':START.isoformat(),'asOf':AS_OF.isoformat(),'historyDays':365,'historicalExpensesTiyn':expense,'seed':20261007}
 (ROOT/'data/manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(report,ensure_ascii=False));return output

if __name__=='__main__':generate()
