"""Read-only Kaspi Gold PDF import. Never stores the PDF or its account number."""
import hashlib
import io
import json
import re
import uuid
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

class KaspiError(ValueError):
    pass

def clean(value):
    return ' '.join(str(value or '').split())

def money(value):
    # Foreign purchases have a second amount in USD/CNY. Only booked KZT counts.
    match=re.search(r'([+\-−])\s*([\d\s\u00a0]+,\d{2})\s*₸',str(value or ''))
    if not match:raise KaspiError('Не удалось распознать сумму в тенге в PDF')
    amount=int(Decimal(re.sub(r'\s','',match[2]).replace(',','.'))*100)
    return -amount if match[1] in ['-','−'] else amount

def parse_pdf(raw, account_id, categories):
    import pdfplumber
    if not raw.startswith(b'%PDF-'):raise KaspiError('Не удалось прочитать PDF выписки')
    tables=[];texts=[]
    try:
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            if not 1<=len(pdf.pages)<=100:raise KaspiError('В PDF должно быть не более 100 страниц')
            for page in pdf.pages:
                text=page.extract_text() or ''
                texts.append(text)
                if len(text)>200000:raise KaspiError('PDF слишком сложный для импорта')
                tables.extend(page.extract_tables())
    except KaspiError:raise
    except Exception:raise KaspiError('Не удалось прочитать PDF. Нужна незашифрованная выписка Kaspi Gold, не скан.')
    text='\n'.join(texts)
    period=re.search(r'по Kaspi Gold за период с\s*(\d{2}\.\d{2}\.\d{2})\s*по\s*(\d{2}\.\d{2}\.\d{2})',text,re.I)
    if not period:raise KaspiError('Нужен PDF выписки Kaspi Gold с таблицей операций, не скан')
    def day(value):
        result=datetime.strptime(value,'%d.%m.%y').date()
        if not date(2000,1,1)<=result<=date.today():raise KaspiError('Проверьте даты периода PDF')
        return result
    start,end=day(period[1]),day(period[2])
    if start>end:raise KaspiError('Проверьте даты периода PDF')
    iban=re.search(r'\bKZ\d{2}[A-Z0-9]{16}\b',text)
    if not iban:raise KaspiError('Не удалось определить счёт в PDF Kaspi')
    opening=closing=None;summary={};records=[];seen=Counter();operation_totals=Counter()
    operation_names={'Пополнение':'Пополнения','Поступление со своего счета':'Поступления со своих счетов',
        'Зачисление кредита':'Зачисления кредитов','Перевод':'Переводы','Перевод на свой счет':'Переводы на свои счета',
        'Покупка':'Покупки','Снятие':'Снятия','Разное':'Разное'}
    for table in tables:
        for row in table:
            if len(row)==2:
                label=clean(row[0])
                if label==f'Доступно на {period[1]}':opening=money(row[1])
                elif label==f'Доступно на {period[2]}':closing=money(row[1])
                elif label in ['Пополнения','Поступления со своих счетов','Зачисления кредитов','Переводы','Переводы на свои счета','Покупки','Снятия','Разное']:
                    summary[label]=money(row[1])
            elif len(row)==4:
                raw_date=clean(row[0])
                if raw_date=='Дата':continue
                if not re.fullmatch(r'\d{2}\.\d{2}\.\d{2}',raw_date):
                    if any('₸' in str(cell or '') for cell in row):
                        raise KaspiError('Не удалось распознать строку PDF. Импорт отменён.')
                    continue
                d=day(raw_date);signed=money(row[1]);op=clean(row[2]);details=clean(row[3])
                if op not in operation_names:raise KaspiError('Неизвестный вид операции Kaspi. Импорт отменён.')
                operation_totals[operation_names[op]]+=signed
                if not start<=d<=end or not 0<abs(signed)<=10000000000:
                    raise KaspiError('Проверьте дату и сумму операции PDF')
                kind='income' if signed>0 else 'expense'
                # Do not guess salary or recurrence from a person-to-person transfer.
                category='shopping' if op=='Покупка' else 'other'
                if category not in categories:category='other'
                description=(op+' · '+details).strip(' ·')[:120]
                canonical=json.dumps([d.isoformat(),signed,op,details],ensure_ascii=False,separators=(',',':'))
                seen[canonical]+=1
                identifier=str(uuid.uuid5(uuid.UUID(account_id),'kaspi:'+canonical+':'+str(seen[canonical])))
                records.append({'id':identifier,'date':d.isoformat(),'description':description,'type':kind,'category':category,'amount':abs(signed),'recurring':False})
                if len(records)>3000:raise KaspiError('Максимум 3000 операций в одном файле')
    if not records or opening is None or closing is None or len(summary)!=8:
        raise KaspiError('Не найдены все операции и итоги PDF. Импорт отменён.')
    income=sum(t['amount'] for t in records if t['type']=='income')
    expenses=sum(t['amount'] for t in records if t['type']=='expense')
    # Summary categories are NET totals: purchase refunds must not disappear.
    if opening+income-expenses!=closing or any(operation_totals[k]!=v for k,v in summary.items()):
        raise KaspiError('Операции PDF не совпадают с итогами банка. Импорт отменён.')
    return records,{'bank':'Kaspi Gold','periodStart':start.isoformat(),'periodEnd':end.isoformat(),
        'opening':opening,'closing':closing,'income':income,'expenses':expenses,'reconciled':True,
        'accountHash':hashlib.sha256(iban[0].encode()).hexdigest()}
