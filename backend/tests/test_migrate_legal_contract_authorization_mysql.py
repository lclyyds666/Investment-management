import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.engine import make_url


MYSQL_TEST_URL_ENV = "LEGAL_CONTRACT_MYSQL_TEST_URL"


def _execute_all(cursor, source: str) -> None:
    cursor.execute(source)
    while cursor.nextset():
        pass


@pytest.mark.skipif(
    not os.environ.get(MYSQL_TEST_URL_ENV),
    reason=f"set {MYSQL_TEST_URL_ENV} to run the real MySQL 8 migration test",
)
def test_real_mysql8_migration_is_repeatable_and_repairs_legacy_data():
    pymysql = pytest.importorskip("pymysql")
    from pymysql.constants import CLIENT

    url = make_url(os.environ[MYSQL_TEST_URL_ENV])
    database_name = f"test_legal_contract_auth_{uuid4().hex}"
    connection_options = {
        "host": url.host or "127.0.0.1",
        "port": url.port or 3306,
        "user": url.username,
        "password": url.password or "",
        "charset": "utf8mb4",
        "autocommit": True,
        "connect_timeout": 5,
    }
    admin = pymysql.connect(**connection_options)
    try:
        with admin.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE `{database_name}` CHARACTER SET utf8mb4 "
                "COLLATE utf8mb4_unicode_ci"
            )
        print(f"MYSQL_TEMP_DATABASE={database_name}")
        database = pymysql.connect(
            **connection_options,
            database=database_name,
            client_flag=CLIENT.MULTI_STATEMENTS,
        )
        try:
            with database.cursor() as cursor:
                cursor.execute("SELECT VERSION()")
                assert cursor.fetchone()[0].startswith("8.")
                _execute_all(cursor, """
                    CREATE TABLE `sys_user_assignment` (
                      `id` INT NOT NULL PRIMARY KEY
                    ) ENGINE=InnoDB;
                    CREATE TABLE `biz_contract` (
                      `id` INT NOT NULL PRIMARY KEY,
                      `company_code` VARCHAR(64) NULL,
                      `organization_code` VARCHAR(64) NULL,
                      `initiator_assignment_id` INT NULL
                    ) ENGINE=InnoDB;
                    CREATE TABLE `legal_case` (
                      `id` BIGINT NOT NULL PRIMARY KEY,
                      `company_code` VARCHAR(64) NULL,
                      `organization_code` VARCHAR(64) NULL,
                      `initiator_assignment_id` INT NULL
                    ) ENGINE=InnoDB;
                    CREATE TABLE `wf_node` (
                      `id` INT NOT NULL PRIMARY KEY
                    ) ENGINE=InnoDB;
                    INSERT INTO `sys_user_assignment` (`id`) VALUES (1);
                    INSERT INTO `biz_contract`
                      (`id`, `company_code`, `organization_code`, `initiator_assignment_id`)
                    VALUES (1, '', NULL, 999), (2, 'supplymanagement', 'supplymanagement', 1);
                    INSERT INTO `legal_case`
                      (`id`, `company_code`, `organization_code`, `initiator_assignment_id`)
                    VALUES (1, NULL, '', 999), (2, 'investment', 'investment.legal_risk', 1);
                    INSERT INTO `wf_node` (`id`) VALUES (1);
                """)
                migration_source = Path(
                    "migrations/20260821_legal_contract_organization_authorization.sql"
                ).read_text(encoding="utf-8")
                _execute_all(cursor, migration_source)
                _execute_all(cursor, migration_source)

                expected_columns = {
                    ("biz_contract", "company_code"),
                    ("biz_contract", "organization_code"),
                    ("biz_contract", "initiator_assignment_id"),
                    ("biz_contract", "workflow_route_version"),
                    ("legal_case", "company_code"),
                    ("legal_case", "organization_code"),
                    ("legal_case", "initiator_assignment_id"),
                    ("wf_node", "candidate_rule"),
                    ("wf_node", "candidate_position_codes"),
                }
                cursor.execute("""
                    SELECT table_name, column_name
                    FROM information_schema.columns
                    WHERE table_schema = %s
                """, (database_name,))
                assert expected_columns.issubset(set(cursor.fetchall()))

                cursor.execute("""
                    SELECT table_name, column_name, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_schema = %s
                """, (database_name,))
                nullability = {
                    (table_name, column_name): (is_nullable, column_default)
                    for table_name, column_name, is_nullable, column_default
                    in cursor.fetchall()
                }
                non_nullable_columns = expected_columns - {
                    ("biz_contract", "initiator_assignment_id"),
                    ("legal_case", "initiator_assignment_id"),
                    ("wf_node", "candidate_position_codes"),
                }
                assert all(
                    nullability[column][0] == "NO"
                    for column in non_nullable_columns
                )
                assert all(
                    nullability[column][0] == "YES"
                    for column in expected_columns - non_nullable_columns
                )
                assert nullability[("biz_contract", "workflow_route_version")][1] == "0"
                assert nullability[("wf_node", "candidate_rule")][1] == "position"

                cursor.execute("""
                    SELECT id, company_code, organization_code,
                           initiator_assignment_id, workflow_route_version
                    FROM biz_contract ORDER BY id
                """)
                assert cursor.fetchall() == (
                    (1, "supplymanagement", "supplymanagement", None, 0),
                    (2, "supplymanagement", "supplymanagement", 1, 0),
                )
                cursor.execute("""
                    SELECT id, company_code, organization_code, initiator_assignment_id
                    FROM legal_case ORDER BY id
                """)
                assert cursor.fetchall() == (
                    (1, "investment", "investment.legal_risk", None),
                    (2, "investment", "investment.legal_risk", 1),
                )
                cursor.execute(
                    "SELECT candidate_rule, candidate_position_codes FROM wf_node WHERE id = 1"
                )
                assert cursor.fetchone() == ("position", None)

                cursor.execute("""
                    SELECT table_name, index_name
                    FROM information_schema.statistics
                    WHERE table_schema = %s AND index_name IN (
                      'ix_biz_contract_company_code',
                      'ix_biz_contract_organization_code',
                      'ix_biz_contract_initiator_assignment_id',
                      'ix_legal_case_company_code',
                      'ix_legal_case_organization_code',
                      'ix_legal_case_initiator_assignment_id'
                    )
                """, (database_name,))
                assert len(set(cursor.fetchall())) == 6
                cursor.execute("""
                    SELECT table_name, constraint_name
                    FROM information_schema.table_constraints
                    WHERE constraint_schema = %s AND constraint_type = 'FOREIGN KEY'
                """, (database_name,))
                assert set(cursor.fetchall()) == {
                    ("biz_contract", "fk_biz_contract_initiator_assignment"),
                    ("legal_case", "fk_legal_case_initiator_assignment"),
                }
        finally:
            database.close()
    finally:
        with admin.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{database_name}`")
        admin.close()
