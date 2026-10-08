"""Настройки SQL Server. .env в backend имеет приоритет над .env в корне."""
import os
from pathlib import Path
from dotenv import load_dotenv
ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
load_dotenv(ROOT.parent / '.env')
SQL_SERVER = os.getenv('DB_SERVER', r'.\SQLEXPRESS')
DATABASE_NAME = os.getenv('DB_DATABASE', 'FinPredictAI_Demo')
DB_DRIVER = os.getenv('DB_DRIVER', 'ODBC Driver 18 for SQL Server')

def escaped(value):
    return '{' + value.replace('}', '}}') + '}'

def connection_string():
    configured=os.getenv('FINPREDICT_MSSQL_CONNECTION','').strip()
    if configured:
        return configured
    parts=[f'DRIVER={escaped(DB_DRIVER)}', f'SERVER={escaped(SQL_SERVER)}',
        f'DATABASE={escaped(DATABASE_NAME)}',
        'TrustServerCertificate='+os.getenv('DB_TRUST_SERVER_CERTIFICATE','yes'),
        'Connection Timeout='+os.getenv('DB_TIMEOUT','10')]
    username=os.getenv('DB_USERNAME','').strip()
    if username:
        parts.extend(['UID='+escaped(username),'PWD='+escaped(os.getenv('DB_PASSWORD',''))])
    else:
        parts.append('Trusted_Connection=yes')
    encrypt=os.getenv('DB_ENCRYPT','yes').strip()
    if encrypt:
        parts.append('Encrypt='+encrypt)
    return ';'.join(parts)+';'
