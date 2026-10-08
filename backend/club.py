"""Membership, goals, statements and private administrator ranking."""
import csv
import hashlib
import io
import json
import math
import secrets
import uuid
import calendar
from datetime import date, datetime, timedelta, timezone
from flask import Blueprint, g, jsonify, request, Response
from ranks import from_accounts, rating, NAMES
from statements import parse, StatementError, safe_csv_cell

PRICE=199000  # tiyn; 1990 KZT per calendar month

def utcnow():return datetime.now(timezone.utc).replace(tzinfo=None)
def iso_utc(value):return value.isoformat(timespec='seconds')+'Z' if value else None

def add_month(value):
    year=value.year+(value.month==12);month=value.month%12+1
    return value.replace(year=year,month=month,day=min(value.day,calendar.monthrange(year,month)[1]))

def entitlement(cursor,user_id):
    cursor.execute('SELECT ExpiresAt,AutoRenew FROM dbo.Subscriptions WHERE UserId=?',user_id)
    row=cursor.fetchone();active=bool(row and row[0]>utcnow())
    return {'premium':active,'plan':'premium' if active else 'free','price':PRICE,'mode':'demo',
        'expiresAt':iso_utc(row[0]) if row else None,'autoRenew':bool(row[1]) if row else False,
        'accountLimit':3 if active else 1,'goalLimit':20 if active else 3}

def account_rows(cursor,user_id,primary):
    cursor.execute('SELECT Id,Name,Opening,Number FROM dbo.Accounts WHERE Id=? OR Id IN (SELECT AccountId FROM dbo.UserAccounts WHERE UserId=?) ORDER BY Id',primary,user_id)
    return [{'id':r[0],'name':r[1],'opening':r[2],'number':r[3]} for r in cursor.fetchall()]

def owned_account(connect, user, identifier=None):
    identifier=identifier or user['accountId']
    with connect() as connection:
        cursor=connection.cursor()
        cursor.execute('SELECT Id FROM dbo.Accounts WHERE Id=? AND (Id=? OR Id IN (SELECT AccountId FROM dbo.UserAccounts WHERE UserId=?))',identifier,user['accountId'],user['id'])
        found=cursor.fetchone()
    return identifier if found else None

def register_club(app,connect,read_data,as_of,history_start,categories,attach,forecast):
    bp=Blueprint('club',__name__)
    def account():return owned_account(connect,g.user,request.args.get('accountId'))
    def must_user():
        if g.user['role']!='user':return jsonify(error='Этот раздел доступен клиентам'),403
    def premium_required(cursor):return entitlement(cursor,g.user['id'])['premium']
    def validate_kaspi(cur,selected,records,meta):
        """Recheck under the account lock at commit; never replace existing history."""
        if not meta:return None
        cur.execute('SELECT Opening,HistoryStartDate,AsOfDate,BankHash FROM dbo.Accounts WHERE Id=?',selected)
        row=cur.fetchone()
        cur.execute('SELECT Id,Date,Type,Amount FROM dbo.Transactions WHERE AccountId=?',selected)
        old=cur.fetchall()
        if old and not row[3]:return 'Для PDF Kaspi выберите пустой счёт. Существующие операции не удаляются.'
        if row[3] and row[3]!=meta['accountHash']:return 'Эта выписка относится к другому банковскому счёту'
        if row[3] and row[1] and meta['periodStart']<row[1].isoformat():
            return 'Более раннюю выписку загрузите в пустой счёт, начиная с самого раннего периода'
        if old:
            existing={r[0] for r in old}
            ledger=[{'date':r[1].isoformat(),'type':r[2],'amount':r[3]} for r in old]+[t for t in records if t['id'] not in existing]
            def balance_before(bound,inclusive=False):
                return row[0]+sum(t['amount'] if t['type']=='income' else -t['amount'] for t in ledger if (t['date']<=bound if inclusive else t['date']<bound))
            if balance_before(meta['periodStart'])!=meta['opening'] or balance_before(meta['periodEnd'],True)!=meta['closing']:
                return 'История счёта не совпадает с PDF. Выберите пустой счёт или проверьте ручные операции.'
        return None
    def member(user):
        with connect() as connection:
            cur=connection.cursor();plan=entitlement(cur,user['id'])
            accounts=account_rows(cur,user['id'],user['accountId'])
            cur.execute('SELECT DemoSourceId FROM dbo.UserProfiles WHERE UserId=?',user['id'])
            profile=cur.fetchone();demo_account=bool(profile and profile[0])
            cur.execute('SELECT Id,Name,Target,Saved,Deadline FROM dbo.Goals WHERE UserId=? ORDER BY Deadline,Id',user['id'])
            goals=[]
            for r in cur.fetchall():
                remaining=max(0,r[2]-r[3]);months=max(1,math.ceil((r[4]-as_of).days/30.44))
                goals.append({'id':r[0],'name':r[1],'target':r[2],'saved':r[3],'deadline':r[4].isoformat(),
                    'progress':round(r[3]/r[2]*100,1),'monthlyRequired':math.ceil(remaining/months),
                    'overdue':r[4]<as_of and remaining>0,'completed':remaining==0})
        payloads=[];dates=[];selected_dates=None
        for a in accounts:
            data=read_data(a['id']);payloads.append(data['account']|{'transactions':data['transactions']})
            dates.append(date.fromisoformat(data['asOf']))
            if a['id']==(request.args.get('accountId') or user['accountId']):selected_dates=data
            a['balance']=a['opening']+sum(t['amount'] if t['type']=='income' else -t['amount'] for t in data['transactions'])
            a['primary']=a['id']==user['accountId']
        return {'demoAccount':demo_account,'subscription':plan,'accounts':accounts,'goals':goals,'rank':from_accounts(payloads,max(dates,default=as_of)),
            'asOf':selected_dates['asOf'] if selected_dates else as_of.isoformat(),
            'historyStart':selected_dates['historyStart'] if selected_dates else history_start.isoformat()}

    @bp.get('/api/club')
    def club():
        forbidden=must_user()
        if forbidden:return forbidden
        return jsonify(member(g.user))

    @bp.post('/api/accounts')
    def create_account():
        forbidden=must_user()
        if forbidden:return forbidden
        data=request.get_json(silent=True) or {}
        if not isinstance(data,dict):return jsonify(error='Некорректные параметры'),400
        name=data.get('name','')
        if not isinstance(name,str) or not 1<=len(name.strip())<=80:return jsonify(error='Укажите название счёта до 80 символов'),400
        identifier=str(uuid.uuid4())
        with connect() as connection:
            cur=connection.cursor()
            cur.execute('SELECT Id FROM dbo.Users WITH (UPDLOCK,HOLDLOCK) WHERE Id=?',g.user['id']);cur.fetchone()
            if not premium_required(cur):return jsonify(error='Для этой функции нужен Premium'),403
            if len(account_rows(cur,g.user['id'],g.user['accountId']))>=3:return jsonify(error='Можно открыть не более 3 счетов'),409
            # A new virtual account has no invented money or seeded transactions.
            number='FP '+secrets.token_hex(6).upper()
            cur.execute('INSERT INTO dbo.Accounts (Id,Name,Opening,Number) VALUES (?,?,?,?)',identifier,name.strip(),0,number)
            cur.execute('INSERT INTO dbo.UserAccounts (UserId,AccountId) VALUES (?,?)',g.user['id'],identifier)
        return jsonify(id=identifier,status='created'),201

    @bp.post('/api/subscription/activate')
    def activate():
        forbidden=must_user()
        if forbidden:return forbidden
        data=request.get_json(silent=True)
        if not isinstance(data,dict) or data.get('confirmDemo') is not True:return jsonify(error='Подтвердите демонстрационное подключение'),400
        expires=add_month(utcnow())
        with connect() as connection:
            cur=connection.cursor()
            cur.execute('SELECT Id FROM dbo.Users WITH (UPDLOCK,HOLDLOCK) WHERE Id=?',g.user['id']);cur.fetchone()
            current=entitlement(cur,g.user['id'])
            if current['premium']:return jsonify(error='Premium уже активен'),409
            if current['expiresAt']:
                cur.execute('UPDATE dbo.Subscriptions SET ExpiresAt=?,AutoRenew=0,Price=? WHERE UserId=?',expires,PRICE,g.user['id'])
            else:cur.execute('INSERT INTO dbo.Subscriptions (UserId,ExpiresAt,AutoRenew,Price,Mode) VALUES (?,?,?,?,?)',g.user['id'],expires,False,PRICE,'demo')
        return jsonify(status='activated',mode='demo',price=PRICE,expiresAt=iso_utc(expires))

    @bp.post('/api/subscription/cancel')
    def cancel():
        forbidden=must_user()
        if forbidden:return forbidden
        # No payment or auto-renewal exists; cancellation ends demo access now.
        with connect() as connection:
            connection.cursor().execute('UPDATE dbo.Subscriptions SET ExpiresAt=?,AutoRenew=0 WHERE UserId=?',utcnow(),g.user['id'])
        return jsonify(status='cancelled')

    @bp.post('/api/goals')
    def goal_create():
        forbidden=must_user()
        if forbidden:return forbidden
        data=request.get_json(silent=True)
        try:
            if not isinstance(data,dict):raise ValueError()
            name=data['name'].strip();target=data['target'];saved=data.get('saved',0);deadline=date.fromisoformat(data['deadline'])
            if not 1<=len(name)<=120 or type(target) is not int or type(saved) is not int or not 0<=saved<=target<=10000000000 or target<=0 or not as_of<deadline<=as_of+timedelta(days=1826):raise ValueError()
        except (ValueError,TypeError,KeyError,AttributeError):return jsonify(error='Проверьте название, сумму и срок цели'),400
        identifier=str(uuid.uuid4())
        with connect() as connection:
            cur=connection.cursor()
            cur.execute('SELECT Id FROM dbo.Users WITH (UPDLOCK,HOLDLOCK) WHERE Id=?',g.user['id']);cur.fetchone()
            limit=entitlement(cur,g.user['id'])['goalLimit']
            cur.execute('SELECT COUNT(*) FROM dbo.Goals WHERE UserId=?',g.user['id'])
            if cur.fetchone()[0]>=limit:return jsonify(error='Достигнут лимит целей для вашего тарифа'),409
            cur.execute('INSERT INTO dbo.Goals (Id,UserId,Name,Target,Saved,Deadline) VALUES (?,?,?,?,?,?)',identifier,g.user['id'],name,target,saved,deadline)
        return jsonify(id=identifier,status='created'),201

    @bp.patch('/api/goals/<identifier>')
    def goal_save(identifier):
        forbidden=must_user()
        if forbidden:return forbidden
        data=request.get_json(silent=True)
        saved=data.get('saved') if isinstance(data,dict) else None
        if type(saved) is not int or not 0<=saved<=10000000000:return jsonify(error='Проверьте сумму накоплений'),400
        with connect() as connection:
            cur=connection.cursor();cur.execute('SELECT Target FROM dbo.Goals WITH (UPDLOCK,HOLDLOCK) WHERE Id=? AND UserId=?',identifier,g.user['id'])
            row=cur.fetchone()
            if not row:return jsonify(error='Цель не найдена'),404
            if saved>row[0]:return jsonify(error='Накопления не могут превышать сумму цели'),400
            cur.execute('UPDATE dbo.Goals SET Saved=? WHERE Id=? AND UserId=?',saved,identifier,g.user['id'])
        return jsonify(status='saved')

    @bp.delete('/api/goals/<identifier>')
    def goal_delete(identifier):
        forbidden=must_user()
        if forbidden:return forbidden
        with connect() as connection:
            cur=connection.cursor();cur.execute('DELETE FROM dbo.Goals WHERE Id=? AND UserId=?',identifier,g.user['id']);deleted=cur.rowcount
        return (jsonify(status='deleted'),200) if deleted else (jsonify(error='Цель не найдена'),404)

    @bp.post('/api/statements/preview')
    def statement_preview():
        forbidden=must_user()
        if forbidden:return forbidden
        selected=account()
        if not selected:return jsonify(error='Счёт не найден'),404
        data=request.get_json(silent=True)
        if not isinstance(data,dict):return jsonify(error='Не удалось прочитать файл выписки'),400
        bounds=read_data(selected)
        try:records,meta=parse(data,selected,categories,date.fromisoformat(bounds['historyStart']),date.fromisoformat(bounds['asOf']),with_metadata=True)
        except StatementError as error:
            message=str(error)
            if message.startswith('Строка '):
                return jsonify(error='Ошибка в строке выписки',line=int(message.split(':')[0].split()[1])),400
            return jsonify(error=message),400
        token=secrets.token_urlsafe(32);identifier=hashlib.sha256(token.encode()).hexdigest()
        with connect() as connection:
            cur=connection.cursor()
            error=validate_kaspi(cur,selected,records,meta)
            if error:return jsonify(error=error),409
            cur.execute('DELETE FROM dbo.StatementPreviews WHERE ExpiresAt<? OR UserId=?',utcnow(),g.user['id'])
            cur.execute('SELECT Id FROM dbo.Transactions WHERE AccountId=?',selected);existing={r[0] for r in cur.fetchall()}
            duplicates=sum(t['id'] in existing for t in records)
            cur.execute('INSERT INTO dbo.StatementPreviews (Id,UserId,AccountId,RowsJson,ExpiresAt) VALUES (?,?,?,?,?)',identifier,g.user['id'],selected,json.dumps({'rows':records,'metadata':meta},ensure_ascii=False),utcnow()+timedelta(minutes=30))
        return jsonify(token=token,accountId=selected,total=len(records),duplicates=duplicates,new=len(records)-duplicates,rows=records[:10],
            income=sum(t['amount'] for t in records if t['type']=='income' and t['id'] not in existing),
            expenses=sum(t['amount'] for t in records if t['type']=='expense' and t['id'] not in existing),
            statement={k:v for k,v in meta.items() if k!='accountHash'} if meta else None)

    @bp.post('/api/statements/commit')
    def statement_commit():
        forbidden=must_user()
        if forbidden:return forbidden
        data=request.get_json(silent=True)
        token=data.get('token') if isinstance(data,dict) else None
        if not isinstance(token,str) or len(token)>128:return jsonify(error='Предпросмотр истёк. Загрузите файл снова.'),400
        identifier=hashlib.sha256(token.encode()).hexdigest()
        with connect() as connection:
            cur=connection.cursor();cur.execute('SELECT AccountId,RowsJson,ExpiresAt FROM dbo.StatementPreviews WITH (UPDLOCK,HOLDLOCK) WHERE Id=? AND UserId=?',identifier,g.user['id'])
            preview=cur.fetchone()
            if not preview or preview[2]<=utcnow():return jsonify(error='Предпросмотр истёк. Загрузите файл снова.'),409
            selected=preview[0]
            # Serialize commits for this account, including distinct overlapping uploads.
            cur.execute('SELECT Id FROM dbo.Accounts WITH (UPDLOCK,HOLDLOCK) WHERE Id=? AND (Id=? OR Id IN (SELECT AccountId FROM dbo.UserAccounts WHERE UserId=?))',selected,g.user['accountId'],g.user['id'])
            if not cur.fetchone():return jsonify(error='Счёт не найден'),404
            cur.execute('SELECT Id FROM dbo.Transactions WHERE AccountId=?',selected);existing={r[0] for r in cur.fetchall()}
            saved=json.loads(preview[1]);records=saved if isinstance(saved,list) else saved['rows']
            meta=saved.get('metadata') if isinstance(saved,dict) else None
            error=validate_kaspi(cur,selected,records,meta)
            if error:return jsonify(error=error),409
            new=[t for t in records if t['id'] not in existing]
            if meta:
                cur.execute('SELECT HistoryStartDate,AsOfDate FROM dbo.Accounts WHERE Id=?',selected)
                dates=cur.fetchone()
                if not existing:
                    cur.execute('UPDATE dbo.Accounts SET Opening=?,HistoryStartDate=?,AsOfDate=?,BankHash=? WHERE Id=?',meta['opening'],date.fromisoformat(meta['periodStart']),date.fromisoformat(meta['periodEnd']),meta['accountHash'],selected)
                else:
                    last=max(dates[1] or as_of,date.fromisoformat(meta['periodEnd']))
                    cur.execute('UPDATE dbo.Accounts SET AsOfDate=? WHERE Id=?',last,selected)
            if new:cur.executemany('INSERT INTO dbo.Transactions (Id,AccountId,Date,Description,Category,Type,Amount,Recurring) VALUES (?,?,?,?,?,?,?,?)',
                [(t['id'],selected,t['date'],t['description'],t['category'],t['type'],t['amount'],t['recurring']) for t in new])
            cur.execute('DELETE FROM dbo.StatementPreviews WHERE Id=? AND UserId=?',identifier,g.user['id'])
        return jsonify(status='imported',added=len(new),duplicates=len(records)-len(new),accountId=selected,period=(meta['periodEnd'] if meta else max(t['date'] for t in records))[:7])

    @bp.get('/api/statements/template')
    def template():
        content='date;description;amount;type;category;recurring\n'+as_of.isoformat()+';Example expense;1500;expense;food;false\n'
        return Response('\ufeff'+content,mimetype='text/csv',headers={'Content-Disposition':'attachment; filename="statement-template.csv"'})

    @bp.get('/api/reports/export')
    def export():
        forbidden=must_user()
        if forbidden:return forbidden
        with connect() as connection:
            if not premium_required(connection.cursor()):return jsonify(error='Для этой функции нужен Premium'),403
        selected=account()
        if not selected:return jsonify(error='Счёт не найден'),404
        payload=read_data(selected);stream=io.StringIO();writer=csv.writer(stream,delimiter=';')
        writer.writerow(['date','description','amount','type','category','recurring'])
        for t in payload['transactions']:
            writer.writerow([t['date'],safe_csv_cell(t['description']),format(t['amount']/100,'.2f'),t['type'],t['category'],str(bool(t['recurring'])).lower()])
        return Response('\ufeff'+stream.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename="finpredict-report.csv"'})

    @bp.get('/api/club/scenarios')
    def scenarios():
        forbidden=must_user()
        if forbidden:return forbidden
        with connect() as connection:
            if not premium_required(connection.cursor()):return jsonify(error='Для этой функции нужен Premium'),403
        selected=account()
        if not selected:return jsonify(error='Счёт не найден'),404
        payload=read_data(selected);last=date.fromisoformat(payload['asOf'])
        payload.update(horizon=90,futureDays=[(last+timedelta(days=i)).isoformat() for i in range(1,91)])
        payload=attach(payload);results=[]
        for scenario,savings in [('base',0),('low',15),('high',0)]:
            projected=forecast(payload|{'scenario':scenario,'savings':savings})
            results.append({'scenario':scenario,'savings':savings,'total':projected['total'],'endBalance':projected['endBalance'],
                'deficitDate':next((d['date'] for d in projected['daily'] if d['balance']<0),None)})
        return jsonify(horizon=90,results=results)

    @bp.get('/api/admin/ranking')
    def ranking():
        try:
            page=int(request.args.get('page','1'));level=request.args.get('level','all')
            if not 1<=page<=100000 or level not in ['all','0','1','2','3','4']:raise ValueError()
        except ValueError:return jsonify(error='Некорректные параметры'),400
        clients={}
        with connect() as connection:
            cur=connection.cursor()
            # One aggregate query for all clients instead of 1000 ML forecasts.
            cur.execute("SELECT u.Id,u.Name,u.Email,a.Id,a.Opening,CONVERT(VARCHAR(7),t.Date,126),COALESCE(SUM(CASE WHEN t.Type='income' THEN t.Amount ELSE 0 END),0),COALESCE(SUM(CASE WHEN t.Type='expense' THEN t.Amount ELSE 0 END),0),a.AsOfDate FROM dbo.Users u JOIN (SELECT UserId,AccountId FROM dbo.UserAccounts UNION SELECT Id,AccountId FROM dbo.Users) own ON own.UserId=u.Id JOIN dbo.Accounts a ON a.Id=own.AccountId LEFT JOIN dbo.Transactions t ON t.AccountId=a.Id AND t.Date<=? WHERE u.Role='user' GROUP BY u.Id,u.Name,u.Email,a.Id,a.Opening,CONVERT(VARCHAR(7),t.Date,126),a.AsOfDate",date.today())
            for r in cur.fetchall():
                client=clients.setdefault(r[0],{'id':r[0],'name':r[1],'email':r[2],'balance':0,'monthly':{},'accounts':set(),'asOf':r[8] or as_of})
                client['asOf']=max(client['asOf'],r[8] or as_of)
                if r[3] not in client['accounts']:client['balance']+=r[4];client['accounts'].add(r[3])
                client['balance']+=r[6]-r[7]
                if r[5]:
                    month=client['monthly'].setdefault(r[5],{'income':0,'expenses':0});month['income']+=r[6];month['expenses']+=r[7]
        ranked=[];distribution=[0]*5
        for c in clients.values():
            rank=rating(c['balance'],c['monthly'],c['asOf']);distribution[rank['level']]+=1
            ranked.append({'id':c['id'],'name':c['name'],'email':c['email'],'balance':c['balance'],'accounts':len(c['accounts']),'rank':rank})
        ranked.sort(key=lambda c:(-c['rank']['score'],-c['balance'],c['id']))
        for i,c in enumerate(ranked,1):c['position']=i
        if level!='all':ranked=[c for c in ranked if c['rank']['level']==int(level)]
        count=len(ranked)
        return jsonify(users=ranked[(page-1)*25:page*25],total=count,page=page,pages=max(1,(count+24)//25),
            distribution=[{'level':i,'name':NAMES[i],'count':v} for i,v in enumerate(distribution)],asOf=as_of.isoformat())

    @bp.get('/api/admin/users/<identifier>/club')
    def admin_club(identifier):
        with connect() as connection:
            cur=connection.cursor();cur.execute("SELECT Id,Name,AccountId FROM dbo.Users WHERE Id=? AND Role='user'",identifier);row=cur.fetchone()
        if not row:return jsonify(error='Клиент не найден'),404
        return jsonify(member({'id':row[0],'name':row[1],'accountId':row[2]}))

    app.register_blueprint(bp)
