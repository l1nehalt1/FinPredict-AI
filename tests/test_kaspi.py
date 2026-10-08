"""Synthetic Kaspi table tests. No real customer's PDF/data is shipped."""
import base64
import unittest
from copy import deepcopy
from datetime import date
from unittest.mock import patch
import test_auth
from kaspi import parse_pdf, KaspiError

ACCOUNT='00000000-0000-0000-0000-000000000001'
TEXT='ВЫПИСКА по Kaspi Gold за период с 08.10.25 по 08.10.26\nKZ123456789012345678'
SUMMARY=[['Доступно на 08.10.25','+ 100,00 ₸'],['Пополнения','+ 50,00 ₸'],
 ['Поступления со своих счетов','+ 0,00 ₸'],['Зачисления кредитов','+ 0,00 ₸'],
 ['Переводы','- 0,00 ₸'],['Переводы на свои счета','- 10,00 ₸'],
 ['Покупки','- 15,00 ₸'],['Снятия','- 0,00 ₸'],['Разное','- 0,00 ₸'],['Доступно на 08.10.26','+ 125,00 ₸']]
ROWS=[['Дата','Сумма','Операция','Детали'],['08.10.26','+ 50,00 ₸','Пополнение','Demo credit'],
 ['07.10.26','- 20,00 ₸\n(- 1,00 USD)','Покупка','Demo shop'],
 ['07.10.26','+ 5,00 ₸','Покупка','Demo refund'],
 ['06.10.26','- 10,00 ₸','Перевод на свой\nсчет','Demo saving']]
class Page:
 def __init__(self,text=TEXT,tables=None):self.text=text;self.tables=tables if tables is not None else [deepcopy(SUMMARY),deepcopy(ROWS)]
 def extract_text(self):return self.text
 def extract_tables(self):return self.tables
class PDF:
 def __init__(self,pages=None):self.pages=pages or [Page('Certificate',[]),Page()]
 def __enter__(self):return self
 def __exit__(self,*args):pass
class ParserTests(unittest.TestCase):
 def parse(self,pdf=None):
  with patch('pdfplumber.open',return_value=pdf or PDF()):
   return parse_pdf(b'%PDF-fake',ACCOUNT,['shopping','other'])
 def test_foreign_currency_refunds_and_opening_reconcile(self):
  rows,meta=self.parse();self.assertEqual(len(rows),4)
  self.assertEqual(rows[1]['amount'],2000);self.assertEqual(rows[2]['type'],'income')
  self.assertEqual(meta['opening']+meta['income']-meta['expenses'],meta['closing'])
  self.assertEqual(meta['closing'],12500);self.assertTrue(meta['reconciled'])
  self.assertEqual(meta['periodEnd'],'2026-10-08');self.assertEqual(len(meta['accountHash']),64)
  self.assertNotIn('KZ123456789012345678',str(meta))
  self.assertTrue(all(not t['recurring'] for t in rows))
 def test_ids_are_repeat_safe_and_account_scoped(self):
  rows,_=self.parse();again,_=self.parse();self.assertEqual(rows,again)
  with patch('pdfplumber.open',return_value=PDF()):
   other,_=parse_pdf(b'%PDF-fake','00000000-0000-0000-0000-000000000002',['shopping','other'])
  self.assertNotEqual(rows[0]['id'],other[0]['id'])
 def test_incomplete_and_changed_summaries_fail_closed(self):
  for tables in [[deepcopy(SUMMARY),deepcopy(ROWS[:-1])],[deepcopy(SUMMARY[:-1]),deepcopy(ROWS)]]:
   with self.assertRaises(KaspiError):self.parse(PDF([Page(tables=tables)]))
  tables=[deepcopy(SUMMARY),deepcopy(ROWS)];tables[0][1][1]='+ 49,00 ₸'
  with self.assertRaises(KaspiError):self.parse(PDF([Page(tables=tables)]))
 def test_scan_future_unknown_operation_and_corrupt_row_fail_closed(self):
  with self.assertRaises(KaspiError):self.parse(PDF([Page('',[])]))
  tables=[deepcopy(SUMMARY),deepcopy(ROWS)];tables[1][1][0]='09.10.99'
  with self.assertRaises(KaspiError):self.parse(PDF([Page(tables=tables)]))
  tables=[deepcopy(SUMMARY),deepcopy(ROWS)];tables[1][1][2]='Unknown operation'
  with self.assertRaises(KaspiError):self.parse(PDF([Page(tables=tables)]))
  tables=[deepcopy(SUMMARY),deepcopy(ROWS)];tables[1][1][0]='broken date'
  with self.assertRaises(KaspiError):self.parse(PDF([Page(tables=tables)]))

class ImportTests(unittest.TestCase):
 setUp=test_auth.AuthTests.setUp
 tearDown=test_auth.AuthTests.tearDown
 csrf=test_auth.AuthTests.csrf
 register=test_auth.AuthTests.register
 request=test_auth.AuthTests.request
 def preview(self,pdf=None,client=None):
  with patch('pdfplumber.open',return_value=pdf or PDF()):
   return self.request(client or self.a,'/api/statements/preview',json={'filename':'kaspi.pdf','content':base64.b64encode(b'%PDF-fake').decode()})
 def commit(self,preview,client=None):
  return self.request(client or self.a,'/api/statements/commit',json={'token':preview.json['token']})
 def test_pdf_preview_commit_dates_balance_and_repeat(self):
  self.register(self.a);preview=self.preview();self.assertEqual(preview.status_code,200)
  self.assertNotIn('accountHash',preview.json['statement'])
  self.assertEqual(self.a.get('/api/data').json['summary']['balance'],0)
  result=self.commit(preview);self.assertEqual(result.status_code,200)
  data=self.a.get('/api/data').json
  self.assertEqual(data['asOf'],'2026-10-08');self.assertEqual(data['historyStart'],'2025-10-08')
  self.assertEqual(data['account']['opening'],10000);self.assertEqual(data['summary']['balance'],12500)
  self.assertEqual(len(data['transactions']),4)
  self.assertEqual(self.a.get('/api/forecast').json['periodStart'],'2026-10-09')
  self.assertEqual(self.a.get('/api/club').json['asOf'],'2026-10-08')
  second=self.preview();self.assertEqual(second.json['new'],0)
  self.assertEqual(self.commit(second).json['added'],0)
  self.assertEqual(self.a.get('/api/data').json['summary']['balance'],12500)
 def test_nonempty_unbound_account_is_not_overwritten(self):
  self.register(self.a)
  self.request(self.a,'/api/transactions',json={'date':'2026-09-01','description':'Manual','amount':200,'type':'expense','category':'food'})
  self.assertEqual(self.preview().status_code,409)
  self.assertEqual(self.a.get('/api/data').json['summary']['balance'],-200)
 def test_changed_account_and_modified_ledger_are_rejected(self):
  self.register(self.a);self.assertEqual(self.commit(self.preview()).status_code,200)
  text=TEXT.replace('KZ123456789012345678','KZ123456789012345679')
  self.assertEqual(self.preview(PDF([Page(text)])).status_code,409)
  self.request(self.a,'/api/transactions',json={'date':'2026-10-08','description':'Manual','amount':100,'type':'expense','category':'food'})
  self.assertEqual(self.preview().status_code,409)
 def test_commit_rechecks_changes_and_is_user_bound(self):
  self.register(self.a);self.register(self.b,'other@example.test');preview=self.preview()
  self.assertEqual(self.commit(preview,self.b).status_code,409)
  self.request(self.a,'/api/transactions',json={'date':'2026-09-01','description':'Changed','amount':200,'type':'expense','category':'food'})
  self.assertEqual(self.commit(preview).status_code,409)
  self.assertEqual(self.a.get('/api/data').json['account']['opening'],0)
 def test_overlapping_extension_imports_only_new_rows(self):
  self.register(self.a)
  first_summary=deepcopy(SUMMARY);first_summary[-1][0]='Доступно на 07.10.26'
  first_rows=deepcopy(ROWS);first_rows[1][0]='07.10.26'
  first=PDF([Page(TEXT.replace('по 08.10.26','по 07.10.26'),[first_summary,first_rows])])
  self.assertEqual(self.commit(self.preview(first)).json['added'],4)
  summary=deepcopy(SUMMARY);summary[0]=['Доступно на 07.10.26','+ 90,00 ₸']
  summary[5][1]='- 0,00 ₸';summary[6][1]='- 20,00 ₸';summary[-1][1]='+ 120,00 ₸'
  rows=deepcopy(first_rows[:-1])+[['08.10.26','- 5,00 ₸','Покупка','New demo purchase']]
  extension=PDF([Page(TEXT.replace('с 08.10.25','с 07.10.26'),[summary,rows])])
  preview=self.preview(extension);self.assertEqual(preview.status_code,200)
  self.assertEqual(preview.json['duplicates'],3);self.assertEqual(preview.json['new'],1)
  self.assertEqual(self.commit(preview).json['added'],1)
  data=self.a.get('/api/data').json
  self.assertEqual(data['summary']['balance'],12000);self.assertEqual(data['account']['opening'],10000)
  self.assertEqual(data['asOf'],'2026-10-08');self.assertEqual(len(data['transactions']),5)
 def test_admin_ranking_and_details_use_imported_account_date(self):
  user=self.register(self.a).json['user'];self.register(self.b,'admin@example.test')
  self.db.execute("UPDATE Users SET Role='admin' WHERE Email='admin@example.test'")
  self.commit(self.preview())
  detail=self.b.get('/api/admin/users/'+user['id']).json
  self.assertEqual(detail['snapshot']['summary']['balance'],12500)
  self.assertEqual(detail['forecast']['periodStart'],'2026-10-09')
  rank=self.b.get('/api/admin/ranking').json['users'][0]
  self.assertEqual(rank['balance'],12500);self.assertEqual(rank['rank'],self.a.get('/api/club').json['rank'])

if __name__=='__main__':unittest.main()
