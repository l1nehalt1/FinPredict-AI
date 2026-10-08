import json
import gzip
import unittest
from pathlib import Path
from test_auth import AuthTests,server
from init_demo import ensure_admin,import_client
from werkzeug.security import generate_password_hash

class AdminTests(unittest.TestCase):
    setUp=AuthTests.setUp
    tearDown=AuthTests.tearDown
    csrf=AuthTests.csrf
    request=AuthTests.request
    register=AuthTests.register
    def admin_login(self):
        with server.connect() as db:ensure_admin(db.cursor(),'admin@example.test',generate_password_hash('admin-pass-123'))
        response=self.request(self.b,'/api/auth/login',json={'email':'admin@example.test','password':'admin-pass-123'})
        self.assertEqual(response.status_code,200);self.assertEqual(response.json['user']['role'],'admin')
    def test_users_cannot_read_admin_endpoints_or_self_promote(self):
        token=self.csrf(self.a)
        r=self.a.post('/api/auth/register',json={'name':'User','email':'user@example.test','password':'test-pass-123','role':'admin'},headers={'X-CSRF-Token':token})
        self.assertEqual(r.json['user']['role'],'user')
        for path in ['/api/admin/users','/api/admin/summary','/api/admin/users/'+r.json['user']['id']]:
            self.assertEqual(self.a.get(path).status_code,403)
    def test_admin_lists_searches_and_views_client_history_and_annual_forecast(self):
        client=self.register(self.a).json['user'];self.admin_login()
        summary=self.b.get('/api/admin/summary');self.assertEqual(summary.status_code,200);self.assertEqual(summary.json['clients'],1)
        users=self.b.get('/api/admin/users?q=a%40example.com').json;self.assertEqual(users['total'],1)
        detail=self.b.get('/api/admin/users/'+client['id']+'?horizon=365')
        self.assertEqual(detail.status_code,200);self.assertEqual(detail.json['forecast']['horizon'],365)
        self.assertEqual(len(detail.json['forecast']['daily']),365)
        self.assertEqual(len(detail.json['snapshot']['transactions']),0)
        self.assertEqual(detail.json['forecast']['periodStart'],'2026-10-08')
        self.assertEqual(detail.json['forecast']['periodEnd'],'2027-10-07')
        self.assertEqual(self.b.get('/api/admin/users?page=0').status_code,400)
        self.assertEqual(self.b.get('/api/admin/users/missing').status_code,404)
    def test_admin_role_required_after_role_change(self):
        self.admin_login()
        self.db.execute("UPDATE Users SET Role='user' WHERE Email='admin@example.test'")
        self.assertEqual(self.b.get('/api/admin/summary').status_code,403)
    def test_existing_customer_cannot_be_replaced_by_admin_setup(self):
        self.register(self.a,'admin@example.test')
        with server.connect() as db:
            with self.assertRaises(ValueError):ensure_admin(db.cursor(),'admin@example.test',generate_password_hash('admin-pass-123'))
        self.assertEqual(self.db.execute("SELECT Role FROM Users").fetchone()[0],'user')
    def test_full_1000_import_idempotence_and_password_login(self):
        root=Path(__file__).resolve().parents[1]/'backend/data'
        manifest=json.loads((root/'manifest.json').read_text())
        hashed=generate_password_hash('demo-pass-123')
        seen=set();row_count=0
        with server.connect() as db,gzip.open(root/'clients_1000.jsonl.gz','rt',encoding='utf-8') as stream:
            cursor=db.cursor()
            for line in stream:
                client=json.loads(line);seen.add(client['id']);row_count+=len(client['transactions'])
                self.assertTrue(import_client(cursor,client,hashed))
                self.assertFalse(import_client(cursor,client,hashed))
                self.assertTrue(all(manifest['historyStart']<=t['date']<=manifest['asOf'] for t in client['transactions']))
        self.assertEqual(len(seen),1000);self.assertEqual(row_count,manifest['transactions'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM Users').fetchone()[0],1000)
        self.assertEqual(self.db.execute('SELECT count(*) FROM Transactions').fetchone()[0],manifest['transactions'])
        r=self.request(self.a,'/api/auth/login',json={'email':'client0001@example.test','password':'demo-pass-123'})
        self.assertEqual(r.status_code,200)
        data=self.a.get('/api/data?period=2025-11');self.assertEqual(data.status_code,200)
        own=self.db.execute('SELECT count(*) FROM Transactions WHERE AccountId=(SELECT AccountId FROM Users WHERE Email=?)',('client0001@example.test',)).fetchone()[0]
        self.assertEqual(len(data.json['transactions']),own)
        self.admin_login()
        listing=self.b.get('/api/admin/users?page=40');self.assertEqual(listing.json['total'],1000);self.assertEqual(len(listing.json['users']),25)
        board=self.b.get('/api/admin/ranking?page=40');self.assertEqual(board.status_code,200)
        self.assertEqual(board.json['total'],1000);self.assertEqual(len(board.json['users']),25)
        self.assertEqual(sum(x['count'] for x in board.json['distribution']),1000)
        self.assertEqual(board.json['users'][0]['position'],976)
        first=self.b.get('/api/admin/ranking').json['users']
        self.assertEqual([c['rank']['score'] for c in first],sorted([c['rank']['score'] for c in first],reverse=True))
    def test_model_holdout_and_annual_projection(self):
        from ml_forecast import metadata,attach
        metrics=metadata();self.assertLess(metrics['trainingThrough'],metrics['validationMonth'])
        self.assertEqual(metrics['validationRows'],1000)
        payload=dict(server.SEED,horizon=365)
        forecast=attach(payload)
        self.assertIn('mlMonthly',forecast)
        self.assertIn('2027-10',forecast['mlMonthly'])

if __name__=='__main__':unittest.main(verbosity=2)
