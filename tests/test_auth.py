"""HTTP/session/isolation integration checks with an in-memory SQL adapter.
Live SQL Server needs a separate validation on the user's Windows computer.
"""
import re
import sqlite3
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import app as server
from werkzeug.security import check_password_hash

class Cursor:
    def __init__(self, db):self.cursor=db.cursor()
    def execute(self,sql,*params):
        sql=sql.replace('dbo.','')
        sql=re.sub(r' WITH \(UPDLOCK,HOLDLOCK\)','',sql)
        if ' OFFSET ? ROWS FETCH NEXT 25 ROWS ONLY' in sql:
            sql=sql.replace(' OFFSET ? ROWS FETCH NEXT 25 ROWS ONLY',' LIMIT 25 OFFSET ?')
        sql=sql.replace('CONVERT(VARCHAR(7),t.Date,126)', "strftime('%Y-%m',t.Date)")
        self.cursor.execute(sql,params)
        return self
    def executemany(self,sql,rows):self.cursor.executemany(sql.replace('dbo.',''),rows);return self
    def fetchone(self):return self.cursor.fetchone()
    def fetchall(self):return self.cursor.fetchall()
    @property
    def rowcount(self):return self.cursor.rowcount
class Connection:
    def __init__(self,db):self.db=db
    def cursor(self):return Cursor(self.db)

class AuthTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:',detect_types=sqlite3.PARSE_DECLTYPES)
        self.db.executescript('''CREATE TABLE Accounts(Id TEXT PRIMARY KEY,Name TEXT,Opening INTEGER,Number TEXT,AsOfDate DATE,HistoryStartDate DATE,BankHash TEXT);
        CREATE TABLE Transactions(Id TEXT PRIMARY KEY,AccountId TEXT,Date DATE,Description TEXT,Category TEXT,Type TEXT,Amount INTEGER,Recurring INTEGER);
        CREATE TABLE Users(Id TEXT PRIMARY KEY,Name TEXT,Email TEXT UNIQUE,PasswordHash TEXT,AccountId TEXT UNIQUE,Role TEXT NOT NULL DEFAULT 'user');
        CREATE TABLE UserProfiles(UserId TEXT PRIMARY KEY,City TEXT,Age INTEGER,Occupation TEXT,Segment TEXT,MonthlyIncome INTEGER,DemoSourceId TEXT UNIQUE);
        CREATE TABLE AuthSessions(TokenHash TEXT PRIMARY KEY,UserId TEXT,ExpiresAt TIMESTAMP);''')
        self.db.executescript('''CREATE TABLE UserAccounts(UserId TEXT,AccountId TEXT UNIQUE,PRIMARY KEY(UserId,AccountId));
        CREATE TABLE Subscriptions(UserId TEXT PRIMARY KEY,ExpiresAt TIMESTAMP,AutoRenew INTEGER,Price INTEGER,Mode TEXT);
        CREATE TABLE Goals(Id TEXT PRIMARY KEY,UserId TEXT,Name TEXT,Target INTEGER,Saved INTEGER,Deadline DATE);
        CREATE TABLE StatementPreviews(Id TEXT PRIMARY KEY,UserId TEXT,AccountId TEXT,RowsJson TEXT,ExpiresAt TIMESTAMP);''')
        @contextmanager
        def connect():
            try:yield Connection(self.db);self.db.commit()
            except Exception:self.db.rollback();raise
        self.patch=patch.object(server,'connect',connect);self.patch.start()
        server.app.config.update(TESTING=True,SECRET_KEY='test-only-secret',SESSION_COOKIE_SECURE=False)
        server._attempts.clear()
        self.a=server.app.test_client();self.b=server.app.test_client()
    def tearDown(self):self.patch.stop();self.db.close()
    def csrf(self,c):return c.get('/api/auth/me').json['csrfToken']
    def register(self,c,email='a@example.com'):
        return c.post('/api/auth/register',json={'name':'Ерасыл','email':email,'password':'test-pass-123'},headers={'X-CSRF-Token':self.csrf(c)})
    def request(self,c,path,method='post',**kwargs):
        return getattr(c,method)(path,headers={'X-CSRF-Token':self.csrf(c)},**kwargs)
    def test_anonymous_cannot_read_or_mutate(self):
        for path in ['/api/data','/api/forecast']:
            self.assertEqual(self.a.get(path).status_code,401)
        self.assertEqual(self.request(self.a,'/api/reset',json={}).status_code,401)
    def test_registration_hash_and_cookie(self):
        r=self.register(self.a);self.assertEqual(r.status_code,201)
        hashed=self.db.execute('SELECT PasswordHash FROM Users').fetchone()[0]
        self.assertNotIn('test-pass-123',hashed);self.assertTrue(check_password_hash(hashed,'test-pass-123'))
        self.assertIn('HttpOnly',r.headers['Set-Cookie']);self.assertIn('SameSite=Lax',r.headers['Set-Cookie'])
        self.assertEqual(self.a.get('/api/auth/me').json['user']['name'],'Ерасыл')
    def test_new_registration_is_empty_even_when_client_requests_demo_money(self):
        r=self.a.post('/api/auth/register',json={'name':'New client','email':'new@example.test','password':'test-pass-123','balance':999999,'demo':True},headers={'X-CSRF-Token':self.csrf(self.a)})
        self.assertEqual(r.status_code,201)
        data=self.a.get('/api/data?period=2026-09').json
        self.assertEqual(data['account']['opening'],0)
        self.assertEqual(data['transactions'],[])
        for key in ['balance','income','expenses','net']:self.assertEqual(data['summary'][key],0)
        self.assertEqual(self.a.get('/api/forecast').json['total'],0)
        club=self.a.get('/api/club').json
        self.assertFalse(club['demoAccount']);self.assertEqual(club['rank']['score'],0)
        self.assertEqual(self.request(self.a,'/api/reset',json={}).status_code,403)
        self.assertEqual(self.a.get('/api/data').json['transactions'],[])

    def test_duplicate_email_case_insensitive(self):
        self.register(self.a)
        r=self.register(self.b,'A@EXAMPLE.COM');self.assertEqual(r.status_code,409)
        self.assertEqual(self.db.execute('SELECT count(*) FROM Users').fetchone()[0],1)
    def test_password_validation(self):
        self.assertEqual(self.a.post('/api/auth/register',json={'name':'X','email':'x@example.com','password':'short'},headers={'X-CSRF-Token':self.csrf(self.a)}).status_code,400)
    def test_csrf_required_for_login_registration_and_mutation(self):
        self.assertEqual(self.a.post('/api/auth/register',json={}).status_code,403)
        self.assertEqual(self.a.post('/api/auth/login',json={}).status_code,403)
        self.register(self.a);self.assertEqual(self.a.post('/api/reset',json={}).status_code,403)
    def test_logout_revokes_session_and_login_restores(self):
        self.register(self.a);cookie=self.a.get_cookie('session').value
        self.assertEqual(self.request(self.a,'/api/auth/logout',json={}).status_code,200)
        self.a.set_cookie('session',cookie)
        self.assertEqual(self.a.get('/api/data').status_code,401)
        r=self.request(self.a,'/api/auth/login',json={'email':'a@example.com','password':'test-pass-123'})
        self.assertEqual(r.status_code,200);self.assertEqual(self.a.get('/api/data').status_code,200)
    def test_wrong_password_is_rejected(self):
        self.register(self.a);self.request(self.a,'/api/auth/logout',json={})
        self.assertEqual(self.request(self.a,'/api/auth/login',json={'email':'a@example.com','password':'wrong'}).status_code,401)
    def test_accounts_operations_reset_and_forecasts_are_isolated(self):
        self.register(self.a);self.register(self.b,'b@example.com')
        a=self.a.get('/api/data?period=2026-09').json;b=self.b.get('/api/data?period=2026-09').json
        self.assertEqual(len(a['transactions']),0)
        self.assertFalse(set(t['id'] for t in a['transactions']) & set(t['id'] for t in b['transactions']))
        row={'date':'2026-09-20','amount':123400,'description':'Тест','type':'expense','category':'food','recurring':False}
        r=self.request(self.a,'/api/transactions',json=row);self.assertEqual(r.status_code,201);identifier=r.json['id']
        self.assertEqual(self.request(self.b,'/api/transactions?id='+identifier,method='delete').status_code,404)
        self.assertEqual(self.b.get('/api/data?period=2026-09').json['summary']['balance'],b['summary']['balance'])
        self.assertEqual(self.a.get('/api/data?period=2026-09').json['summary']['balance'],a['summary']['balance']-123400)
        self.assertEqual(self.request(self.b,'/api/reset',json={}).status_code,403)
        self.assertIn(identifier,[t['id'] for t in self.a.get('/api/data').json['transactions']])
        for horizon in (30,60,90):
            self.assertEqual(self.a.get('/api/forecast?horizon='+str(horizon)).status_code,200)
        self.assertEqual(self.request(self.a,'/api/transactions?id='+identifier,method='delete').status_code,200)
        self.assertEqual(self.request(self.a,'/api/reset',json={}).status_code,403)
    def test_session_expiry(self):
        self.register(self.a)
        self.db.execute("UPDATE AuthSessions SET ExpiresAt='2000-01-01 00:00:00'")
        self.assertEqual(self.a.get('/api/data').status_code,401)
    def test_rate_limit(self):
        self.csrf(self.a)
        for _ in range(12):self.request(self.a,'/api/auth/login',json={'email':'missing@example.com','password':'wrong'})
        self.assertEqual(self.request(self.a,'/api/auth/login',json={}).status_code,429)

if __name__=='__main__':unittest.main(verbosity=2)
