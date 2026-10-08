"""Bootstrap behavior tests with a stateful ODBC double; no live SQL Server."""
import importlib
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import init_db

class OdbcError(Exception):
    pass

class Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.last = None
        self.closed = False
    def execute(self, sql, *params):
        self.last = sql
        self.connection.queries.append((sql, params))
        engine = self.connection.engine
        if sql.startswith('CREATE DATABASE'):
            if not self.connection.autocommit:
                raise OdbcError('CREATE DATABASE in a transaction')
            engine.creates += 1
            if engine.create_failure:
                raise OdbcError('No database permission')
            engine.exists = True
        elif 'CREATE TABLE' in sql:
            if engine.schema_failure:
                raise OdbcError('Schema denied')
            engine.schema_runs += 1
        return self
    def fetchone(self):
        return (1 if self.connection.engine.exists else None,)
    def nextset(self):
        return None
    def close(self):
        self.closed = True

class Connection:
    def __init__(self, engine, value, autocommit):
        self.engine, self.value, self.autocommit = engine, value, autocommit
        self.queries = []
        self.commits = self.rollbacks = 0
        self.closed = False
        self.the_cursor = Cursor(self)
    def cursor(self):return self.the_cursor
    def commit(self):self.commits += 1
    def rollback(self):self.rollbacks += 1
    def close(self):self.closed = True

class Odbc:
    Error = OdbcError
    def __init__(self, exists=False, schema_failure=False, create_failure=False):
        self.exists, self.schema_failure, self.create_failure = exists, schema_failure, create_failure
        self.creates = self.schema_runs = 0
        self.connections = []
    def connect(self, value, autocommit=False, timeout=10):
        connection = Connection(self, value, autocommit)
        self.connections.append(connection)
        return connection

class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.value = 'Driver={ODBC Driver 18 for SQL Server};Server=localhost;Database=FinPredictAI;UID=user;PWD={a;b}}c}'
        init_db._initialized = False
    def run_init(self, engine):
        with patch.dict(sys.modules, {'pyodbc': engine}):
            init_db.initialize_database(self.value)
    def test_creation_uses_master_and_autocommit(self):
        engine=Odbc()
        self.run_init(engine)
        self.assertTrue(engine.connections[0].autocommit)
        self.assertIn('Database={master}',engine.connections[0].value)
        self.assertIn('PWD={a;b}}c}',engine.connections[0].value)
        self.assertFalse(engine.connections[1].autocommit)
        self.assertEqual(engine.creates,1)
        self.assertEqual(engine.connections[1].commits,1)
        self.assertTrue(all(c.closed and c.the_cursor.closed for c in engine.connections))
    def test_rerun_keeps_existing_database(self):
        engine=Odbc()
        self.run_init(engine)
        self.run_init(engine)
        self.assertEqual(engine.creates,1)
        self.assertEqual(engine.schema_runs,2)
        self.assertTrue(all('DROP ' not in sql.upper() and 'DELETE ' not in sql.upper()
                            for c in engine.connections for sql,_ in c.queries))
    def test_database_creation_failure_prevents_schema_connection(self):
        engine=Odbc(create_failure=True)
        with self.assertRaises(OdbcError):self.run_init(engine)
        self.assertEqual(len(engine.connections),1)
        self.assertTrue(engine.connections[0].closed)
    def test_schema_failure_rolls_back_and_closes(self):
        engine=Odbc(schema_failure=True)
        with self.assertRaises(OdbcError):self.run_init(engine)
        self.assertEqual(engine.connections[1].rollbacks,1)
        self.assertEqual(engine.connections[1].commits,0)
        self.assertTrue(engine.connections[1].closed)
    def test_failed_initialization_can_retry(self):
        with patch.object(init_db,'initialize_database',side_effect=[OdbcError('offline'), 'FinPredictAI']) as call:
            with self.assertRaises(OdbcError):init_db.ensure_initialized()
            self.assertFalse(init_db._initialized)
            init_db.ensure_initialized()
            self.assertTrue(init_db._initialized)
            self.assertEqual(call.call_count,2)
    def test_parallel_startup_runs_initializer_once(self):
        with patch.object(init_db,'initialize_database',return_value='FinPredictAI') as call:
            threads=[threading.Thread(target=init_db.ensure_initialized) for _ in range(8)]
            for thread in threads:thread.start()
            for thread in threads:thread.join()
            self.assertEqual(call.call_count,1)
    def test_replaces_aliases_and_duplicate_database_attributes(self):
        value='Driver={A;B};Initial Catalog=Old;Database=X;SERVER=.\\SQLEXPRESS;PWD={p;}}q}'
        target=init_db.for_database(value,'master')
        self.assertNotIn('Initial Catalog',target)
        self.assertNotIn('Database=X',target)
        self.assertIn('Driver={A;B}',target)
        self.assertIn('PWD={p;}}q}',target)
        self.assertEqual(target.count('Database='),1)
    def test_invalid_braced_password_is_rejected(self):
        with self.assertRaises(ValueError):init_db.for_database('Server=localhost;PWD={unterminated','master')
    def test_attach_database_is_rejected(self):
        with self.assertRaises(ValueError):init_db.for_database('Server=localhost;AttachDbFilename=file.mdf','master')
    def test_schema_has_repeat_safe_creation_and_a_lock(self):
        schema=(Path(__file__).resolve().parents[1]/'backend/schema_mssql.sql').read_text()
        self.assertIn('sys.sp_getapplock',schema)
        for table in ['Accounts','Categories','Transactions']:
            self.assertIn("IF OBJECT_ID(N'dbo.%s', N'U') IS NULL"%table,schema)
        self.assertIn('WHERE NOT EXISTS',schema)

if __name__=='__main__':unittest.main(verbosity=2)
