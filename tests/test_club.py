"""HTTP membership and import regression tests using the shared SQL adapter."""
import base64
import io
import json
import unittest
from datetime import datetime
from unittest.mock import patch
import test_auth
from club import add_month
from ranks import rating
from statements import parse, StatementError
from openpyxl import Workbook

server=test_auth.server
class ClubTests(unittest.TestCase):
    setUp=test_auth.AuthTests.setUp
    tearDown=test_auth.AuthTests.tearDown
    csrf=test_auth.AuthTests.csrf
    register=test_auth.AuthTests.register
    request=test_auth.AuthTests.request
    def customer(self):
        self.assertEqual(self.register(self.a).status_code,201)
        return self.a.get('/api/auth/me').json['user']
    def premium(self,client=None):
        return self.request(client or self.a,'/api/subscription/activate',json={'confirmDemo':True})
    def extra(self,name='Savings'):
        r=self.request(self.a,'/api/accounts',json={'name':name});self.assertEqual(r.status_code,201);return r.json['id']
    def csv(self,text=None):
        text=text or 'date;description;amount;type;category;recurring\n2026-09-10;Lunch;1250.50;expense;food;false\n2026-09-11;Salary;200000;income;salary;true\n'
        return {'filename':'statement.csv','content':base64.b64encode(text.encode()).decode()}
    def preview(self,account=None,payload=None,client=None):
        return self.request(client or self.a,'/api/statements/preview'+('?accountId='+account if account else ''),json=payload or self.csv())
    def goal(self,name='Laptop',client=None):
        return self.request(client or self.a,'/api/goals',json={'name':name,'target':30000000,'saved':5000000,'deadline':'2027-01-07'})

    def test_free_entitlements_and_primary_account(self):
        self.customer();r=self.a.get('/api/club');self.assertEqual(r.status_code,200)
        self.assertEqual(r.json['subscription']['accountLimit'],1);self.assertEqual(r.json['subscription']['goalLimit'],3)
        self.assertEqual(len(r.json['accounts']),1);self.assertTrue(r.json['accounts'][0]['primary'])
        self.assertEqual(self.request(self.a,'/api/accounts',json={'name':'X'}).status_code,403)
        self.assertEqual(self.a.get('/api/reports/export').status_code,403)
        self.assertEqual(self.a.get('/api/club/scenarios').status_code,403)
    def test_activation_requires_csrf_and_explicit_demo_confirmation(self):
        self.customer()
        self.assertEqual(self.a.post('/api/subscription/activate',json={'confirmDemo':True}).status_code,403)
        self.assertEqual(self.request(self.a,'/api/subscription/activate',json={'plan':'premium','price':0}).status_code,400)
        before=self.a.get('/api/club').json['rank']
        r=self.premium();self.assertEqual(r.status_code,200);self.assertEqual(r.json['price'],199000);self.assertEqual(r.json['mode'],'demo')
        self.assertEqual(before,self.a.get('/api/club').json['rank'])
        self.assertEqual(self.premium().status_code,409)
    def test_three_accounts_are_enforced_and_empty(self):
        self.customer();self.premium();one=self.extra();two=self.extra('Travel')
        self.assertEqual(self.request(self.a,'/api/accounts',json={'name':'Fourth'}).status_code,409)
        for account in [one,two]:
            r=self.a.get('/api/data?period=2026-09&accountId='+account)
            self.assertEqual(r.status_code,200);self.assertEqual(r.json['summary']['balance'],0);self.assertEqual(r.json['transactions'],[])
            self.assertEqual(self.a.get('/api/forecast?accountId='+account).json['total'],0)
    def test_account_isolation_for_every_route(self):
        self.customer();self.premium();extra=self.extra();self.register(self.b,'b@example.com')
        for path in ['/api/data','/api/forecast','/api/reports/export','/api/club/scenarios']:
            if 'reports' in path or 'scenarios' in path:self.premium(self.b)
            self.assertEqual(self.b.get(path+'?accountId='+extra).status_code,404)
        self.assertEqual(self.preview(extra,client=self.b).status_code,404)
        payload={'date':'2026-09-10','description':'X','amount':500,'type':'expense','category':'food'}
        self.assertEqual(self.request(self.b,'/api/transactions?accountId='+extra,json=payload).status_code,404)
        saved=self.request(self.a,'/api/transactions?accountId='+extra,json=payload);self.assertEqual(saved.status_code,201)
        self.assertEqual(self.request(self.b,'/api/transactions?accountId='+extra+'&id='+saved.json['id'],method='delete').status_code,404)
        self.assertEqual(self.request(self.a,'/api/reset?accountId='+extra,json={}).status_code,403)
    def test_cancel_and_expiry_preserve_accounts_goals_and_data(self):
        self.customer();self.premium();extra=self.extra();self.goal()
        self.preview(extra)
        self.request(self.a,'/api/subscription/cancel',json={})
        data=self.a.get('/api/club').json;self.assertFalse(data['subscription']['premium']);self.assertEqual(len(data['accounts']),2);self.assertEqual(len(data['goals']),1)
        self.assertEqual(self.a.get('/api/data?accountId='+extra).status_code,200)
        self.assertEqual(self.request(self.a,'/api/accounts',json={'name':'Forbidden'}).status_code,403)
        self.assertEqual(self.a.get('/api/reports/export?accountId='+extra).status_code,403)
        self.assertEqual(self.premium().status_code,200)
        self.db.execute("UPDATE Subscriptions SET ExpiresAt='2020-01-01 00:00:00'")
        self.assertFalse(self.a.get('/api/club').json['subscription']['premium'])
    def test_goals_limits_saved_progress_and_isolation(self):
        self.customer();self.register(self.b,'b@example.com')
        goal=self.goal().json['id'];self.goal('Trip');self.goal('Buffer')
        self.assertEqual(self.goal('Fourth').status_code,409)
        self.assertEqual(self.request(self.b,'/api/goals/'+goal,method='patch',json={'saved':10}).status_code,404)
        self.assertEqual(self.request(self.b,'/api/goals/'+goal,method='delete').status_code,404)
        self.assertEqual(self.request(self.a,'/api/goals/'+goal,method='patch',json={'saved':30000001}).status_code,400)
        self.assertEqual(self.request(self.a,'/api/goals/'+goal,method='patch',json={'saved':30000000}).status_code,200)
        g=next(g for g in self.a.get('/api/club').json['goals'] if g['id']==goal)
        self.assertTrue(g['completed']);self.assertEqual(g['progress'],100);self.assertEqual(g['monthlyRequired'],0)
        self.premium();self.assertEqual(self.goal('Fourth').status_code,201)
        self.assertEqual(self.request(self.a,'/api/goals/'+goal,method='delete').status_code,200)
    def test_goals_validation_and_manual_savings_do_not_move_money(self):
        self.customer();before=self.a.get('/api/data').json['summary']['balance']
        self.goal();self.assertEqual(before,self.a.get('/api/data').json['summary']['balance'])
        for payload in [[],{}, {'name':'X','target':True,'deadline':'2027-01-01'}, {'name':'X','target':50,'saved':-1,'deadline':'2027-01-01'}, {'name':'X','target':50,'deadline':'2020-01-01'}]:
            self.assertEqual(self.request(self.a,'/api/goals',json=payload).status_code,400)
    def test_statement_preview_does_not_mutate_and_commit_is_repeat_safe(self):
        self.customer();self.premium();extra=self.extra()
        r=self.preview(extra);self.assertEqual(r.status_code,200);self.assertEqual(r.json['new'],2)
        self.assertEqual(self.a.get('/api/data?accountId='+extra).json['transactions'],[])
        token=r.json['token'];r=self.request(self.a,'/api/statements/commit',json={'token':token});self.assertEqual(r.status_code,200);self.assertEqual(r.json['added'],2)
        self.assertEqual(r.json['accountId'],extra);self.assertEqual(r.json['period'],'2026-09')
        self.assertEqual(self.a.get('/api/data?accountId='+extra).json['summary']['balance'],19874950)
        self.assertEqual(self.request(self.a,'/api/statements/commit',json={'token':token}).status_code,409)
        repeated=self.preview(extra);self.assertEqual(repeated.json['duplicates'],2);self.assertEqual(repeated.json['new'],0)
        committed=self.request(self.a,'/api/statements/commit',json={'token':repeated.json['token']});self.assertEqual(committed.json['added'],0)
    def test_statement_tokens_are_user_bound_and_expire(self):
        self.customer();self.register(self.b,'b@example.com');token=self.preview().json['token']
        self.assertEqual(self.request(self.b,'/api/statements/commit',json={'token':token}).status_code,409)
        self.db.execute("UPDATE StatementPreviews SET ExpiresAt='2020-01-01 00:00:00'")
        self.assertEqual(self.request(self.a,'/api/statements/commit',json={'token':token}).status_code,409)
    def test_import_is_atomic_on_bad_row_and_handles_signed_amounts(self):
        self.customer();before=len(self.a.get('/api/data').json['transactions'])
        bad='date;description;amount;type;category\n2026-09-01;Good;10;expense;food\n2027-01-01;Future;20;expense;food\n'
        r=self.preview(payload=self.csv(bad));self.assertEqual(r.status_code,400);self.assertEqual(r.json['line'],3)
        self.assertEqual(len(self.a.get('/api/data').json['transactions']),before)
        text='date;description;amount\n01.09.2026;Shopping;-1500,25\n02.09.2026;Payment;2000\n'
        r=self.preview(payload=self.csv(text));self.assertEqual(r.status_code,200);self.assertEqual(r.json['rows'][0]['amount'],150025);self.assertEqual(r.json['rows'][0]['type'],'expense')
    def test_xlsx_with_real_date_and_numeric_cells(self):
        self.customer();book=Workbook();sheet=book.active
        sheet.append(['date','description','amount','type','category'])
        sheet.append([datetime(2026,9,12),'Groceries',123.45,'expense','food'])
        buffer=io.BytesIO();book.save(buffer);book.close()
        r=self.preview(payload={'filename':'statement.xlsx','content':base64.b64encode(buffer.getvalue()).decode()})
        self.assertEqual(r.status_code,200);self.assertEqual(r.json['rows'][0]['amount'],12345)
    def test_export_premium_ownership_and_spreadsheet_formula_neutralization(self):
        self.customer();self.premium();extra=self.extra()
        self.request(self.a,'/api/transactions?accountId='+extra,json={'date':'2026-09-01','description':'=HYPERLINK("bad")','amount':123,'type':'expense','category':'food'})
        r=self.a.get('/api/reports/export?accountId='+extra);self.assertEqual(r.status_code,200)
        self.assertIn("'=HYPERLINK",r.get_data(as_text=True));self.assertIn('1.23',r.get_data(as_text=True))
    def test_premium_scenarios_compute_three_distinct_results(self):
        self.customer();self.premium()
        account=self.a.get('/api/club').json['accounts'][0]['id']
        with server.connect() as connection:server.seed(connection.cursor(),reset=True,account_id=account,name='Fixture')
        r=self.a.get('/api/club/scenarios')
        self.assertEqual(r.status_code,200);self.assertEqual(len(r.json['results']),3)
        totals=[x['total'] for x in r.json['results']];self.assertLess(totals[1],totals[0]);self.assertGreater(totals[2],totals[0])
    def test_admin_ranking_is_private_and_counts_all_accounts(self):
        user=self.customer();self.premium();extra=self.extra();self.register(self.b,'b@example.com')
        self.assertEqual(self.a.get('/api/admin/ranking').status_code,403)
        self.assertEqual(server.app.test_client().get('/api/admin/ranking').status_code,401)
        self.db.execute("UPDATE Users SET Role='admin' WHERE Email='b@example.com'")
        r=self.b.get('/api/admin/ranking');self.assertEqual(r.status_code,200);self.assertEqual(r.json['total'],1)
        ranked=r.json['users'][0];self.assertEqual(ranked['accounts'],2);self.assertEqual(ranked['rank'],self.a.get('/api/club').json['rank'])
        self.assertEqual(sum(x['count'] for x in r.json['distribution']),1)
        club=self.b.get('/api/admin/users/'+user['id']+'/club');self.assertEqual(len(club.json['accounts']),2)
        detail=self.b.get('/api/admin/users/'+user['id']+'?accountId='+extra);self.assertEqual(detail.status_code,200);self.assertEqual(detail.json['snapshot']['summary']['balance'],0)
        summary=self.b.get('/api/admin/summary');self.assertEqual(summary.json['clients'],1)
        self.assertEqual(self.b.get('/api/admin/ranking?level=9').status_code,400)
        self.assertEqual(self.request(self.b,'/api/accounts',json={'name':'X'}).status_code,403)
    def test_file_bounds_empty_unknown_extension_and_precision(self):
        self.customer()
        for data in [{'filename':'evil.exe','content':'QQ=='},{'filename':'x.csv','content':'!'},self.csv('date;description;amount\n'),self.csv('date;description;amount\n2026-09-01;X;NaN\n'),self.csv('date;description;amount\n2026-09-01;X;1.001\n')]:
            self.assertEqual(self.preview(payload=data).status_code,400)
        huge='x'*(2*1024*1024+1);self.assertEqual(self.preview(payload=self.csv(huge)).status_code,400)
    def test_real_import_respects_request_limit_beyond_original_16kb(self):
        self.customer();text='date;description;amount;type;category\n'+''.join(f'2026-09-01;Item {i};10;expense;food\n' for i in range(800))
        r=self.preview(payload=self.csv(text));self.assertEqual(r.status_code,200);self.assertEqual(r.json['new'],800)

class RankTests(unittest.TestCase):
    def test_thresholds_and_rating_invariance_under_currency_scale(self):
        asof=server.AS_OF;monthly={f'2026-{i:02d}':{'income':10000,'expenses':7000} for i in range(4,10)}
        r=rating(21000,monthly,asof);self.assertEqual(r['score'],100);self.assertEqual(r['name'],'Магнат')
        scaled={k:{t:v*100 for t,v in m.items()} for k,m in monthly.items()}
        self.assertEqual(r['score'],rating(2100000,scaled,asof)['score'])
        self.assertEqual(sum(x['points'] for x in r['components']),r['score'])
    def test_current_partial_month_and_future_months_do_not_boost_rank(self):
        asof=server.AS_OF;monthly={'2026-10':{'income':999999,'expenses':0},'2027-01':{'income':999999,'expenses':0}}
        r=rating(999999,monthly,asof);self.assertEqual(r['level'],0);self.assertTrue(r['provisional'])
    def test_calendar_month_expiry_clips_month_end(self):
        self.assertEqual(add_month(datetime(2026,1,31)),datetime(2026,2,28));self.assertEqual(add_month(datetime(2026,12,31)),datetime(2027,1,31))
    def test_same_file_preserves_two_identical_operations_and_stable_ids(self):
        text='date;description;amount;type;category\n2026-09-01;Cafe;100;expense;cafe\n2026-09-01;Cafe;100;expense;cafe\n'
        payload={'filename':'x.csv','content':base64.b64encode(text.encode()).decode()}
        rows=parse(payload,'11111111-1111-1111-1111-111111111111',server.CATEGORIES,server.HISTORY_START,server.AS_OF)
        self.assertEqual(len(rows),2);self.assertNotEqual(rows[0]['id'],rows[1]['id']);self.assertEqual(rows,parse(payload,'11111111-1111-1111-1111-111111111111',server.CATEGORIES,server.HISTORY_START,server.AS_OF))

if __name__=='__main__':unittest.main(verbosity=2)
