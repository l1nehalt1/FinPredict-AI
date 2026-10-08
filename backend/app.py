"""CPython/MS SQL deployment of the same application.

The database and missing tables are created automatically through pyodbc.
Configure backend/config.py or FINPREDICT_MSSQL_CONNECTION. Demo data seeds itself once. This local entry
binds to 127.0.0.1 by default; use authenticated hosting before exposing it.
"""
import json
import os
import uuid
import secrets
import hashlib
import hmac
import re
import time
from collections import defaultdict, deque
from threading import Lock
from contextlib import contextmanager
from datetime import date, timedelta, datetime, timezone
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, session, g
from werkzeug.security import generate_password_hash, check_password_hash
from finance import dashboard, forecast
from ml_forecast import attach, metadata
from config import DATABASE_NAME, connection_string
from init_db import ensure_initialized, for_database
from club import register_club, owned_account

ROOT = Path(__file__).resolve().parent
SEED = json.loads((ROOT / 'demo-data.json').read_text(encoding='utf-8'))
AS_OF = date.fromisoformat(SEED['asOf'])
HISTORY_START = date.fromisoformat(SEED.get('historyStart',min(t['date'] for t in SEED['transactions'])))
CATEGORIES = {'housing','food','cafe','shopping','transport','services','health','leisure','salary','freelance','other'}
app = Flask(__name__, static_folder=str(ROOT.parent / 'dist-mssql'))
app.config['MAX_CONTENT_LENGTH'] = 16384
secret_path = ROOT / '.session-secret'
if not os.getenv('FINPREDICT_SECRET_KEY'):
    try:
        with secret_path.open('x', encoding='utf-8') as stream:
            stream.write(secrets.token_hex(32))
        secret_path.chmod(0o600)
    except FileExistsError:
        pass
app.secret_key = os.getenv('FINPREDICT_SECRET_KEY') or secret_path.read_text().strip()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.getenv('FINPREDICT_COOKIE_SECURE', 'no').lower() == 'yes',
    PERMANENT_SESSION_LIFETIME=timedelta(days=7))
_attempts = defaultdict(deque)
_attempt_lock = Lock()
DUMMY_HASH = generate_password_hash(secrets.token_urlsafe(32))

def limited():
    # Process-local throttling for this single-process demonstration.
    key = request.remote_addr or 'unknown'
    now = time.monotonic()
    with _attempt_lock:
        if len(_attempts) > 4096:
            for old in list(_attempts):
                if not _attempts[old] or now - _attempts[old][-1] > 60:
                    del _attempts[old]
        attempts = _attempts[key]
        while attempts and now - attempts[0] > 60:
            attempts.popleft()
        if len(attempts) >= 12:
            return True
        attempts.append(now)
    return False

def json_object():
    value=request.get_json(silent=True)
    return value if isinstance(value,dict) else {}

def csrf_token():
    if 'csrf' not in session:
        session['csrf'] = secrets.token_urlsafe(32)
    return session['csrf']

def establish_login(cursor, user_id):
    session.clear()
    session.permanent = True
    token = secrets.token_urlsafe(32)
    session['auth_token'] = token
    session['csrf'] = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7)
    cursor.execute('INSERT INTO dbo.AuthSessions (TokenHash,UserId,ExpiresAt) VALUES (?,?,?)', token_hash, user_id, expires)

def current_user():
    token = session.get('auth_token')
    if not token:
        return None
    with connect() as connection:
        cursor = connection.cursor()
        cursor.execute('SELECT u.Id,u.Name,u.Email,u.AccountId,u.Role FROM dbo.Users u JOIN dbo.AuthSessions s ON s.UserId=u.Id WHERE s.TokenHash=? AND s.ExpiresAt>?',
            hashlib.sha256(token.encode()).hexdigest(), datetime.now(timezone.utc).replace(tzinfo=None))
        row = cursor.fetchone()
    return {'id':row[0], 'name':row[1], 'email':row[2], 'accountId':row[3], 'role':row[4]} if row else None

@app.get('/api/auth/me')
def auth_me():
    return jsonify(user=current_user(), csrfToken=csrf_token())

@app.post('/api/auth/register')
def register():
    if limited():
        return jsonify(error='Слишком много попыток. Подождите минуту.'),429
    payload = json_object()
    name, email, password = payload.get('name',''), payload.get('email',''), payload.get('password','')
    if not all(isinstance(v,str) for v in (name,email,password)):
        return jsonify(error='Проверьте имя, email и пароль'),400
    name, email = name.strip(), email.strip().lower()
    if not 1 <= len(name) <= 120 or len(email)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or not 8 <= len(password) <= 128:
        return jsonify(error='Укажите имя, корректный email и пароль от 8 до 128 символов'),400
    password_hash = generate_password_hash(password)
    user_id, account_id = str(uuid.uuid4()), str(uuid.uuid4())
    with connect() as connection:
        cursor = connection.cursor()
        cursor.execute('SELECT Id FROM dbo.Users WITH (UPDLOCK,HOLDLOCK) WHERE Email=?',email)
        if cursor.fetchone():
            return jsonify(error='Этот email уже зарегистрирован'),409
        cursor.execute('INSERT INTO dbo.Accounts (Id,Name,Opening,Number) VALUES (?,?,?,?)',
            account_id,name,0,'FP '+secrets.token_hex(6).upper())
        cursor.execute('INSERT INTO dbo.Users (Id,Name,Email,PasswordHash,AccountId) VALUES (?,?,?,?,?)',user_id,name,email,password_hash,account_id)
        establish_login(cursor,user_id)
    return jsonify(user={'id':user_id,'name':name,'email':email,'role':'user'},csrfToken=csrf_token()),201

@app.post('/api/auth/login')
def login():
    if limited():
        return jsonify(error='Слишком много попыток. Подождите минуту.'),429
    payload=json_object()
    email,password=payload.get('email',''),payload.get('password','')
    if not isinstance(email,str) or not isinstance(password,str) or len(email)>254 or len(password)>128:
        return jsonify(error='Неверный email или пароль'),401
    with connect() as connection:
        cursor=connection.cursor()
        cursor.execute('SELECT Id,Name,Email,PasswordHash,Role FROM dbo.Users WHERE Email=?',email.strip().lower())
        row=cursor.fetchone()
        valid=check_password_hash(row[3] if row else DUMMY_HASH,password)
        if not row or not valid:
            return jsonify(error='Неверный email или пароль'),401
        old=session.get('auth_token')
        if old:
            cursor.execute('DELETE FROM dbo.AuthSessions WHERE TokenHash=?',hashlib.sha256(old.encode()).hexdigest())
        establish_login(cursor,row[0])
    return jsonify(user={'id':row[0],'name':row[1],'email':row[2],'role':row[4]},csrfToken=csrf_token())

@app.post('/api/auth/logout')
def logout():
    token=session.get('auth_token')
    if token:
        with connect() as connection:
            connection.cursor().execute('DELETE FROM dbo.AuthSessions WHERE TokenHash=?',hashlib.sha256(token.encode()).hexdigest())
    session.clear()
    return jsonify(user=None,csrfToken=csrf_token())

@contextmanager
def connect():
    import pyodbc
    ensure_initialized()
    db = pyodbc.connect(for_database(connection_string(), DATABASE_NAME), timeout=10)
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def seed(cursor, reset=False, account_id=None, name=None):
    account_id = account_id or g.user["accountId"]
    # SERIALIZABLE range lock prevents concurrent requests from seeding twice.
    cursor.execute('SELECT Id FROM dbo.Accounts WITH (UPDLOCK,HOLDLOCK) WHERE Id=?', account_id)
    exists = cursor.fetchone()
    if exists and not reset:
        return
    if reset:
        cursor.execute('DELETE FROM dbo.Transactions WHERE AccountId=?', account_id)
    if not exists:
        cursor.execute('INSERT INTO dbo.Accounts (Id,Name,Opening,Number) VALUES (?,?,?,?)',
                       account_id, name or g.user['name'], SEED['account']['opening'], SEED['account']['number'])
    else:
        cursor.execute('UPDATE dbo.Accounts SET Opening=? WHERE Id=?',SEED['account']['opening'],account_id)
    cursor.executemany('INSERT INTO dbo.Transactions (Id,AccountId,Date,Description,Category,Type,Amount,Recurring) VALUES (?,?,?,?,?,?,?,?)',
        [(str(uuid.uuid5(uuid.UUID(account_id),t['id'])),account_id,t['date'],t['description'],t['category'],t['type'],t['amount'],t['recurring']) for t in SEED['transactions']])

def read_data(account_id=None):
    account_id=account_id or g.get("account_id",g.user["accountId"])
    with connect() as connection:
        cursor=connection.cursor()
        cursor.execute('SELECT Name,Opening,Number,AsOfDate,HistoryStartDate FROM dbo.Accounts WHERE Id=?',account_id)
        row=cursor.fetchone()
        account={'name':row[0],'opening':row[1],'number':row[2]}
        cursor.execute('SELECT Id,Date,Description,Category,Type,Amount,Recurring FROM dbo.Transactions WHERE AccountId=? ORDER BY Date DESC,Id DESC',account_id)
        transactions=[{'id':r[0],'date':r[1].isoformat(),'description':r[2],'category':r[3],'type':r[4],'amount':r[5],'recurring':int(r[6])} for r in cursor.fetchall()]
    return {'account':account,'transactions':transactions,'asOf':(row[3] or AS_OF).isoformat(),'historyStart':(row[4] or HISTORY_START).isoformat()}

@app.before_request
def protect_api():
    if not request.path.startswith('/api/'):
        return
    if request.path=='/api/statements/preview':
        request.max_content_length=3*1024*1024
    if request.method in {'POST','DELETE','PUT','PATCH'}:
        expected = session.get('csrf','')
        supplied = request.headers.get('X-CSRF-Token','')
        if not expected or not hmac.compare_digest(expected,supplied):
            return jsonify(error='Обновите страницу и повторите действие'),403
    if not request.path.startswith('/api/auth/'):
        g.user = current_user()
        if not g.user:
            return jsonify(error='Войдите в аккаунт'),401
        if request.path.startswith('/api/admin/') and g.user['role']!='admin':
            return jsonify(error='Доступ разрешён только администратору'),403
        if request.path in ['/api/data','/api/forecast','/api/transactions','/api/reset']:
            g.account_id=owned_account(connect,g.user,request.args.get('accountId'))
            if not g.account_id:return jsonify(error='Счёт не найден'),404

@app.get('/api/config')
def config_api():
    return jsonify(asOf=AS_OF.isoformat(),historyStart=HISTORY_START.isoformat(),horizons=[30,60,90,180,365],model=metadata())

@app.get('/api/admin/summary')
def admin_summary():
    with connect() as connection:
        cursor=connection.cursor()
        cursor.execute("SELECT u.Id,a.Opening,COALESCE(SUM(CASE WHEN t.Type='income' THEN t.Amount ELSE 0 END),0),COALESCE(SUM(CASE WHEN t.Type='expense' THEN t.Amount ELSE 0 END),0),COUNT(t.Id) FROM dbo.Users u JOIN (SELECT UserId,AccountId FROM dbo.UserAccounts UNION SELECT Id,AccountId FROM dbo.Users) own ON own.UserId=u.Id JOIN dbo.Accounts a ON a.Id=own.AccountId LEFT JOIN dbo.Transactions t ON t.AccountId=a.Id WHERE u.Role='user' GROUP BY u.Id,a.Id,a.Opening")
        rows=cursor.fetchall()
    balances={}
    for r in rows:balances[r[0]]=balances.get(r[0],0)+r[1]+r[2]-r[3]
    return jsonify(clients=len(balances),transactions=sum(r[4] for r in rows),totalBalance=sum(r[1]+r[2]-r[3] for r in rows),totalExpenses=sum(r[3] for r in rows),negativeBalances=sum(1 for v in balances.values() if v<0),historyStart=HISTORY_START.isoformat(),asOf=AS_OF.isoformat(),model=metadata())

@app.get('/api/admin/users')
def admin_users():
    query=request.args.get('q','').strip()[:120]
    try:
        page=int(request.args.get('page','1'))
        if not 1<=page<=100000:raise ValueError()
    except ValueError:return jsonify(error='Некорректные параметры'),400
    # Escape LIKE metacharacters; input is always bound.
    escaped=query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_').replace('[','\\[')
    term='%'+escaped+'%'
    where="u.Role='user' AND (u.Name LIKE ? ESCAPE '\\' OR u.Email LIKE ? ESCAPE '\\' OR COALESCE(p.City,'') LIKE ? ESCAPE '\\')"
    with connect() as connection:
        cursor=connection.cursor()
        cursor.execute('SELECT COUNT(*) FROM dbo.Users u LEFT JOIN dbo.UserProfiles p ON p.UserId=u.Id WHERE '+where,term,term,term)
        count=cursor.fetchone()[0]
        cursor.execute("SELECT u.Id,u.Name,u.Email,COALESCE(p.City,''),p.Age,COALESCE(p.Occupation,''),COALESCE(p.Segment,''),COALESCE(p.MonthlyIncome,0) FROM dbo.Users u LEFT JOIN dbo.UserProfiles p ON p.UserId=u.Id WHERE "+where+" ORDER BY u.Name,u.Id OFFSET ? ROWS FETCH NEXT 25 ROWS ONLY",term,term,term,(page-1)*25)
        users=[{'id':r[0],'name':r[1],'email':r[2],'city':r[3],'age':r[4],'occupation':r[5],'segment':r[6],'monthlyIncome':r[7]} for r in cursor.fetchall()]
    return jsonify(users=users,total=count,page=page,pages=max(1,(count+24)//25))

@app.get('/api/admin/users/<identifier>')
def admin_client(identifier):
    try:
        horizon=int(request.args.get('horizon','365'))
        if horizon not in [30,60,90,180,365]:raise ValueError()
    except ValueError:return jsonify(error='Некорректные параметры прогноза'),400
    with connect() as connection:
        cursor=connection.cursor()
        cursor.execute("SELECT u.Id,u.Name,u.Email,u.AccountId,p.City,p.Age,p.Occupation,p.Segment,p.MonthlyIncome FROM dbo.Users u LEFT JOIN dbo.UserProfiles p ON p.UserId=u.Id WHERE u.Id=? AND u.Role='user'",identifier)
        row=cursor.fetchone()
    if not row:return jsonify(error='Клиент не найден'),404
    user={'id':row[0],'name':row[1],'email':row[2],'city':row[4],'age':row[5],'occupation':row[6],'segment':row[7],'monthlyIncome':row[8]}
    selected=owned_account(connect,{'id':row[0],'accountId':row[3]},request.args.get('accountId'))
    if not selected:return jsonify(error='Счёт не найден'),404
    payload=read_data(selected);last=date.fromisoformat(payload['asOf']);start=last.replace(day=1)
    payload.update(period=last.strftime('%Y-%m'),previousPeriod=(start-timedelta(days=1)).strftime('%Y-%m'),days=[(start+timedelta(days=i)).isoformat() for i in range(last.day)])
    snapshot=dashboard(payload)
    payload.update(horizon=horizon,scenario='base',savings=0,futureDays=[(last+timedelta(days=i)).isoformat() for i in range(1,horizon+1)])
    return jsonify(user=user,snapshot=snapshot,forecast=forecast(attach(payload)))

@app.get('/api/data')
def data_api():
    payload=read_data();last=date.fromisoformat(payload['asOf'])
    period=request.args.get('period') or last.strftime('%Y-%m')
    try:
        chosen=date.fromisoformat(period+'-01')
        valid=payload['historyStart'][:7]<=period<=payload['asOf'][:7]
    except (ValueError,TypeError):
        valid=False
    if not valid:
        return jsonify(error='Выберите доступный месяц'),400
    start=date.fromisoformat(period+'-01')
    days=[];d=start
    while d.strftime('%Y-%m')==period and d<=last:
        days.append(d.isoformat());d+=timedelta(days=1)
    payload.update(period=period,previousPeriod=(start-timedelta(days=1)).strftime('%Y-%m'),days=days)
    return jsonify(dashboard(payload))

@app.get('/api/forecast')
def forecast_api():
    try:
        horizon=int(request.args.get('horizon','30'));savings=int(request.args.get('savings','0'))
        scenario=request.args.get('scenario','base')
        if horizon not in [30,60,90,180,365] or scenario not in ['base','low','high'] or not 0<=savings<=30:
            raise ValueError()
    except ValueError:
        return jsonify(error='Некорректные параметры прогноза'),400
    payload=read_data();last=date.fromisoformat(payload['asOf'])
    payload.update(horizon=horizon,savings=savings,scenario=scenario,
        futureDays=[(last+timedelta(days=i)).isoformat() for i in range(1,horizon+1)])
    return jsonify(forecast(attach(payload)))

@app.post('/api/transactions')
def create_transaction():
    account_id=g.get("account_id",g.user["accountId"])
    payload=json_object()
    try:
        amount=payload['amount'];description=payload['description'].strip();d=date.fromisoformat(payload['date'])
        if type(amount) is not int or not 0<amount<=10000000000 or not 1<=len(description)<=120:
            raise ValueError()
        bounds=read_data(account_id)
        if payload['type'] not in ['income','expense'] or payload['category'] not in CATEGORIES or not bounds['historyStart']<=d.isoformat()<=bounds['asOf']:
            raise ValueError()
        if type(payload.get('recurring',False)) is not bool:
            raise ValueError()
    except (KeyError,ValueError,TypeError,AttributeError):
        return jsonify(error='Проверьте сумму, описание, дату и категорию'),400
    identifier=str(uuid.uuid4())
    with connect() as connection:
        cursor=connection.cursor()
        cursor.execute('INSERT INTO dbo.Transactions (Id,AccountId,Date,Description,Category,Type,Amount,Recurring) VALUES (?,?,?,?,?,?,?,?)',
            identifier,account_id,d,description,payload['category'],payload['type'],amount,payload.get('recurring',False))
    return jsonify(id=identifier,status='saved'),201

@app.delete('/api/transactions')
def delete_transaction():
    account_id=g.get("account_id",g.user["accountId"])
    identifier=request.args.get('id')
    if not identifier:return jsonify(error='Операция не указана'),400
    with connect() as connection:
        cursor=connection.cursor()
        cursor.execute('DELETE FROM dbo.Transactions WHERE AccountId=? AND Id=?',account_id,identifier)
        deleted=cursor.rowcount
    return (jsonify(status='deleted'),200) if deleted else (jsonify(error='Операция не найдена'),404)

@app.post('/api/reset')
def reset_demo():
    if g.account_id!=g.user['accountId']:return jsonify(error='Восстановление доступно только для основного демо-счёта'),403
    with connect() as connection:
        cursor=connection.cursor()
        cursor.execute('SELECT DemoSourceId FROM dbo.UserProfiles WHERE UserId=?',g.user['id'])
        profile=cursor.fetchone()
        if not profile or not profile[0]:return jsonify(error='Восстановление доступно только для демо-клиентов'),403
        seed(cursor,reset=True)
    return jsonify(status='reset')

@app.errorhandler(Exception)
def failure(error):
    from werkzeug.exceptions import HTTPException
    if isinstance(error,HTTPException):return jsonify(error=error.description),error.code
    app.logger.exception('FinPredict request failed')
    return jsonify(error='Не удалось выполнить действие. Проверьте подключение к SQL Server.'),500

@app.after_request
def no_cache(response):
    if request.path.startswith('/api/'):
        response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    return response

@app.get('/')
def home():return send_from_directory(app.static_folder,'index.html')

@app.get('/<path:path>')
def assets(path):return send_from_directory(app.static_folder,path)

register_club(app,lambda:connect(),read_data,AS_OF,HISTORY_START,CATEGORIES,attach,forecast)

if __name__=='__main__':
    try:
        ensure_initialized()
        if os.getenv('FINPREDICT_BOOTSTRAP_DEMO','yes').lower()=='yes':
            from init_demo import main as import_demo
            import_demo()
    except Exception as error:
        print('Не удалось подготовить базу. Проверьте имя SQL Server в backend/config.py, '
              'установку ODBC Driver 18 и права подключения/создания базы.')
        print('Тип ошибки:', type(error).__name__)
        print('Подробности:', str(error))
        raise SystemExit(1)
    print(f'База {DATABASE_NAME} и таблицы готовы. Откройте http://127.0.0.1:{os.environ.get("PORT", "8000")}')
    app.run(host='127.0.0.1',port=int(os.environ.get('PORT','8000')),debug=False)
