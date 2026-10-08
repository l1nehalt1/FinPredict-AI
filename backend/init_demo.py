"""Idempotent import of 1000 generated clients and a separately protected admin.
Run: python backend/init_demo.py. Passwords are chosen locally, never bundled.
"""
import gzip
import json
import os
import uuid
from getpass import getpass
from pathlib import Path
from werkzeug.security import generate_password_hash
from config import DATABASE_NAME,connection_string
from init_db import ensure_initialized,for_database
ROOT=Path(__file__).resolve().parent

def password(prompt,env):
 value=os.getenv(env) or getpass(prompt)
 if not 8<=len(value)<=128:raise ValueError('Пароль должен содержать 8–128 символов')
 return value

def ensure_admin(cursor,email,password_hash):
 cursor.execute('SELECT Id,Role FROM dbo.Users WITH (UPDLOCK,HOLDLOCK) WHERE Email=?',email)
 row=cursor.fetchone()
 if row:
  if row[1]!='admin':raise ValueError('Email администратора занят клиентом. Укажите другой FINPREDICT_ADMIN_EMAIL.')
  return False
 uid,aid=str(uuid.uuid4()),str(uuid.uuid4())
 cursor.execute('INSERT INTO dbo.Accounts (Id,Name,Opening,Number) VALUES (?,?,?,?)',aid,'Администратор',0,'ADMIN')
 cursor.execute('INSERT INTO dbo.Users (Id,Name,Email,PasswordHash,AccountId,Role) VALUES (?,?,?,?,?,?)',uid,'Администратор',email,password_hash,aid,'admin')
 return True

def import_client(cursor,client,password_hash):
 cursor.execute('SELECT UserId FROM dbo.UserProfiles WITH (UPDLOCK,HOLDLOCK) WHERE DemoSourceId=?',client['sourceId'])
 if cursor.fetchone():return False
 cursor.execute('SELECT Id FROM dbo.Users WITH (UPDLOCK,HOLDLOCK) WHERE Email=?',client['email'])
 if cursor.fetchone():raise ValueError('Email уже занят: '+client['email'])
 cursor.execute('INSERT INTO dbo.Accounts (Id,Name,Opening,Number) VALUES (?,?,?,?)',client['accountId'],client['name'],client['opening'],client['number'])
 cursor.execute('INSERT INTO dbo.Users (Id,Name,Email,PasswordHash,AccountId,Role) VALUES (?,?,?,?,?,?)',client['id'],client['name'],client['email'],password_hash,client['accountId'],'user')
 cursor.execute('INSERT INTO dbo.UserProfiles (UserId,City,Age,Occupation,Segment,MonthlyIncome,DemoSourceId) VALUES (?,?,?,?,?,?,?)',client['id'],client['city'],client['age'],client['occupation'],client['segment'],client['monthlyIncome'],client['sourceId'])
 cursor.executemany('INSERT INTO dbo.Transactions (Id,AccountId,Date,Description,Category,Type,Amount,Recurring) VALUES (?,?,?,?,?,?,?,?)',[(t['id'],client['accountId'],t['date'],t['description'],t['category'],t['type'],t['amount'],t['recurring']) for t in client['transactions']])
 return True

def main():
 import pyodbc
 ensure_initialized()
 email=os.getenv('FINPREDICT_ADMIN_EMAIL','admin@finpredict.local').strip().lower()
 import re
 if len(email)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):raise ValueError('Некорректный email администратора')
 db=pyodbc.connect(for_database(connection_string(),DATABASE_NAME),timeout=10)
 try:
  cursor=db.cursor()
  cursor.execute('SELECT Id,Role FROM dbo.Users WHERE Email=?',email);admin=cursor.fetchone()
  if admin and admin[1]!='admin':raise ValueError('Email занят клиентом: укажите другой FINPREDICT_ADMIN_EMAIL')
  cursor.execute('SELECT COUNT(*) FROM dbo.UserProfiles WHERE DemoSourceId IS NOT NULL');imported=cursor.fetchone()[0]
  expected=json.loads((ROOT/'data/manifest.json').read_text())['clients']
  if admin and imported>=expected:
   print('Администратор и 1000 клиентов уже готовы. Данные сохранены.');return
  if not admin:
   secret=password('Задайте пароль администратора (минимум 8 символов): ','FINPREDICT_ADMIN_PASSWORD')
   ensure_admin(cursor,email,generate_password_hash(secret));db.commit()
  shared=password('Задайте пароль демонстрационных клиентов (минимум 8 символов): ','FINPREDICT_DEMO_PASSWORD') if imported<expected else None
  added=0
  with gzip.open(ROOT/'data/clients_1000.jsonl.gz','rt',encoding='utf-8') as stream:
   for index,line in enumerate(stream,1):
    client=json.loads(line)
    cursor.execute('SELECT UserId FROM dbo.UserProfiles WHERE DemoSourceId=?',client['sourceId'])
    if cursor.fetchone():continue
    # A unique salt is used even though this demo batch shares a chosen password.
    if import_client(cursor,client,generate_password_hash(shared)):added+=1
    db.commit()
    if index%50==0:print(f'Подготовлено {index}/{expected} клиентов...')
  print(f'Готово. Добавлено клиентов: {added}. Администратор: {email}. Откройте сайт и войдите.')
 except Exception:
  db.rollback();raise
 finally:db.close()
if __name__=='__main__':main()
