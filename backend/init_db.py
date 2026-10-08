"""Создание FinPredictAI и недостающих таблиц через pyodbc.

Запуск отдельно: python backend/init_db.py.
При запуске backend/app.py инициализация вызывается автоматически.
Существующие операции и таблицы не удаляются и не пересоздаются.
"""
import re
import threading
from pathlib import Path
from config import DATABASE_NAME, connection_string

_lock = threading.Lock()
_initialized = False


def _attributes(value):
    """Разделить ODBC-атрибуты, сохранив ; и }} внутри значений в скобках."""
    parts, start, index, braced = [], 0, 0, False
    while index < len(value):
        char = value[index]
        if braced:
            if char == "}":
                if index + 1 < len(value) and value[index + 1] == "}":
                    index += 2
                    continue
                braced = False
        elif char == "{" and "=" in value[start:index] and not value[start:index].partition("=")[2].strip():
            braced = True
        elif char == ";":
            if value[start:index].strip():
                parts.append(value[start:index].strip())
            start = index + 1
        index += 1
    if braced:
        raise ValueError("Незакрытые фигурные скобки в строке ODBC-подключения")
    if value[start:].strip():
        parts.append(value[start:].strip())
    return parts


def for_database(value, database):
    """Поменять только базу, сохранив сервер, пароль и параметры соединения."""
    parts = []
    for attribute in _attributes(value):
        key, separator, _ = attribute.partition("=")
        if not separator:
            raise ValueError("Некорректный атрибут ODBC-подключения")
        normalized = "".join(key.lower().split())
        if normalized == "attachdbfilename":
            raise ValueError("Используйте Server и Database вместо AttachDbFilename")
        if normalized not in {"database", "initialcatalog"}:
            parts.append(attribute)
    parts.append("Database={" + database.replace("}", "}}") + "}")
    return ";".join(parts)


def _drain(cursor):
    while cursor.nextset():
        pass


def initialize_database(value=None):
    """Создать базу и схему. При ошибке схемы откатить изменения таблиц."""
    try:
        import pyodbc
    except ImportError as error:
        raise RuntimeError("Установите библиотеки: python -m pip install -r backend/requirements.txt") from error
    value = value or connection_string()
    schema = Path(__file__).with_name("schema_mssql.sql").read_text(encoding="utf-8")
    master = pyodbc.connect(for_database(value, "master"), autocommit=True, timeout=10)
    try:
        cursor = master.cursor()
        try:
            cursor.execute("SELECT DB_ID(?)", DATABASE_NAME)
            exists = cursor.fetchone()[0] is not None
            if not exists:
                # CREATE DATABASE must be outside an explicit/implicit transaction.
                # The identifier is a fixed application constant, not user input.
                identifier = "[" + DATABASE_NAME.replace("]", "]]") + "]"
                try:
                    cursor.execute("CREATE DATABASE " + identifier)
                    _drain(cursor)
                except pyodbc.Error:
                    # A second process may have created the database meanwhile.
                    cursor.execute("SELECT DB_ID(?)", DATABASE_NAME)
                    if cursor.fetchone()[0] is None:
                        raise
        finally:
            cursor.close()
    finally:
        master.close()

    database = pyodbc.connect(for_database(value, DATABASE_NAME), autocommit=False, timeout=10)
    try:
        cursor = database.cursor()
        try:
            # GO is an SSMS batch separator; it is not sent to the ODBC driver.
            batches = re.split(r"^\s*GO\s*(?:--[^\n]*)?$", schema, flags=re.MULTILINE | re.IGNORECASE)
            for batch in batches:
                if batch.strip():
                    cursor.execute(batch)
                    _drain(cursor)
            database.commit()
        except Exception:
            database.rollback()
            raise
        finally:
            cursor.close()
    finally:
        database.close()
    return DATABASE_NAME


def ensure_initialized():
    """Один успешный запуск на процесс, включая запуск через WSGI."""
    global _initialized
    if _initialized:
        return
    with _lock:
        if not _initialized:
            initialize_database()
            _initialized = True


if __name__ == "__main__":
    try:
        initialize_database()
    except Exception as error:
        print("Не удалось подготовить базу. Проверьте имя сервера в backend/config.py, "
              "ODBC Driver 18 и права подключения/создания базы.")
        # Do not print connection strings, which may contain a SQL password.
        print("Тип ошибки:", type(error).__name__)
        raise SystemExit(1)
    print(f"База {DATABASE_NAME} и таблицы готовы. Существующие данные сохранены.")
