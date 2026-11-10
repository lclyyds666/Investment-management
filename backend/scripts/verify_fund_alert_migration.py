"""Validate the migration only in a disposable, explicitly named local schema."""
from pathlib import Path
import argparse

import pymysql

from app.core.config import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True)
    args = parser.parse_args()
    settings = Settings(_env_file=args.env_file)
    schema = "scm_fund_alert_validation_20261109"
    assert schema != settings.DB_NAME
    connection = pymysql.connect(host=settings.DB_HOST, port=settings.DB_PORT,
                                 user=settings.DB_USER, password=settings.DB_PASSWORD,
                                 autocommit=True)
    created = False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT VERSION()")
            print("MySQL", cursor.fetchone()[0])
            cursor.execute("SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s", (schema,))
            if cursor.fetchone():
                raise RuntimeError("Validation schema already exists; refusing to modify it")
            cursor.execute("CREATE DATABASE `scm_fund_alert_validation_20261109`")
            created = True
            cursor.execute("USE `scm_fund_alert_validation_20261109`")
            for table in ("sys_user", "biz_fund_transaction"):
                cursor.execute(f"CREATE TABLE `{table}` (id INT NOT NULL PRIMARY KEY) ENGINE=InnoDB")
                cursor.execute(f"INSERT INTO `{table}` VALUES (1), (2)")
            migration = (Path(__file__).resolve().parents[1] / "migrations/20261010_fund_alert_receipts.sql").read_text(encoding="utf-8")
            cursor.execute(migration)
            cursor.execute(migration)
            cursor.execute("INSERT INTO biz_fund_alert_receipt (user_id,fund_id,alert_date,stage) VALUES (1,1,'2026-11-09','due_soon'),(2,2,'2026-11-09','overdue')")
            cursor.execute("DELETE FROM biz_fund_transaction WHERE id=1")
            cursor.execute("SELECT COUNT(*) FROM biz_fund_alert_receipt WHERE fund_id=1")
            assert cursor.fetchone()[0] == 0, "Fund cascade failed"
            cursor.execute("DELETE FROM sys_user WHERE id=2")
            cursor.execute("SELECT COUNT(*) FROM biz_fund_alert_receipt")
            assert cursor.fetchone()[0] == 0, "User cascade failed"
            print("Migration twice and both deletion cascades: PASS")
    finally:
        if created:
            with connection.cursor() as cursor:
                cursor.execute("DROP DATABASE `scm_fund_alert_validation_20261109`")
                print("Disposable validation schema removed")
        connection.close()


if __name__ == "__main__":
    main()
