"""Opt-in real MySQL migration acceptance against a disposable database.

Set MYSQL_ACCEPTANCE_PORT to a dedicated test server (not a production server).
"""

import os
import uuid
from dataclasses import replace
from pathlib import Path

import pymysql
import pytest

from common.migrations import MySqlMigration, MySQLMigrationRunner, load_migration_module


@pytest.fixture
def mysql_db():
    port = os.getenv("MYSQL_ACCEPTANCE_PORT")
    if not port:
        pytest.skip("set MYSQL_ACCEPTANCE_PORT for disposable real MySQL acceptance")
    options = {
        "host": "127.0.0.1",
        "port": int(port),
        "user": "root",
        "password": "",
        "charset": "utf8mb4",
        "connect_timeout": 5,
    }
    name = "memory_acceptance_" + uuid.uuid4().hex
    with pymysql.connect(**options) as db:
        with db.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4")
    try:
        yield lambda: pymysql.connect(database=name, **options)
    finally:
        with pymysql.connect(**options) as db:
            with db.cursor() as cursor:
                cursor.execute(f"DROP DATABASE `{name}`")


def migrations():
    directory = Path(__file__).parents[1] / "iot_diagnosis/mysql_migrations"
    return [
        MySqlMigration.of(load_migration_module(path)) for path in sorted(directory.glob("0*.py"))
    ]


def test_new_mysql_memory_cleanup_is_idempotent(mysql_db):
    runner = MySQLMigrationRunner(migrations(), service="memory-acceptance")
    runner.ensure(mysql_db)
    runner.ensure(mysql_db)
    with mysql_db() as db, db.cursor() as cursor:
        cursor.execute("SHOW TABLES")
        tables = {row[0] for row in cursor.fetchall()}
        assert "fault_case" not in tables and "fault_case_feedback" not in tables
        assert {"knowledge_document", "device", "diagnosis_record"} <= tables
        cursor.execute("SELECT COUNT(*) FROM schema_migrations")
        assert cursor.fetchone()[0] == 3


def test_existing_mysql_cleanup_recovers_partial_ddl_without_losing_documents(mysql_db):
    versions = migrations()
    MySQLMigrationRunner(versions[:2], service="memory-acceptance").ensure(mysql_db)
    with mysql_db() as db, db.cursor() as cursor:
        cursor.execute(
            "INSERT INTO knowledge_document (source,source_id,title,content,created_at) VALUES ('official','doc1','title','preserved document','now')"
        )
        cursor.execute(
            "INSERT INTO device (device_id,device_type,name,created_at) VALUES ('d1','ESP32','preserved device','now')"
        )
        cursor.execute(
            "INSERT INTO fault_case (fault_id,device_type,fault_type,fault_name,symptoms_json,logs_json,cause,solution,verified,verified_by,source,created_at,updated_at) VALUES ('f1','ESP32','mqtt','legacy','[]','[]','old','old',1,'human','human_verified','now','now')"
        )
        cursor.execute(
            "INSERT INTO fault_case_feedback VALUES ('fb1','f1','dia1','cmd1','d1','failed','{}','now')"
        )
        db.commit()

    def interrupted(cursor):
        cursor.execute("DROP TABLE IF EXISTS fault_case_feedback")
        raise RuntimeError("injected interruption after first DDL")

    with pytest.raises(RuntimeError, match="injected interruption"):
        MySQLMigrationRunner(
            [*versions[:2], replace(versions[2], upgrade=interrupted)], service="memory-acceptance"
        ).ensure(mysql_db)
    with mysql_db() as db, db.cursor() as cursor:
        cursor.execute("SELECT version FROM schema_migrations ORDER BY version")
        assert cursor.fetchall() == ((1,), (2,))
    runner = MySQLMigrationRunner(versions, service="memory-acceptance")
    runner.ensure(mysql_db)
    runner.ensure(mysql_db)
    with mysql_db() as db, db.cursor() as cursor:
        cursor.execute("SHOW TABLES")
        tables = {row[0] for row in cursor.fetchall()}
        assert "fault_case" not in tables and "fault_case_feedback" not in tables
        cursor.execute("SELECT content FROM knowledge_document WHERE source_id='doc1'")
        assert cursor.fetchone()[0] == "preserved document"
        cursor.execute("SELECT name FROM device WHERE device_id='d1'")
        assert cursor.fetchone()[0] == "preserved device"
