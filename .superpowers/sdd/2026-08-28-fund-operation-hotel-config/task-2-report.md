# Task 2 Report: Fund Domain Model, Validation, and Aggregation

## Status

Completed the standalone fund-domain layer requested by Task 2.

## Delivered Files

- `backend/app/models/fund.py`: `FundTransaction` SQLAlchemy model for the `biz_fund_transaction` ledger.
- `backend/app/schemas/fund.py`: input, update, output, and summary schemas plus transaction-category validation constants.
- `backend/app/services/fund.py`: pure maturity-state and summary aggregation functions.
- `backend/migrations/20260828_fund_management.sql`: idempotent MySQL table and index migration.
- `backend/tests/test_fund_management.py`: boundary and validation coverage.

## Domain Rules Implemented

- `increase` accepts `bank_credit`, `company_loan`, `customer_payment`, `own_funds`, and `other`.
- `usage` accepts `business_payment`, `expense`, `principal_interest_payment`, and `other`.
- Amount must be strictly positive; bank credit and company loans require `maturity_date`.
- Only bank credit and company loans can transition to `settled`; a settlement date cannot precede the occurrence date.
- Settlement only suppresses maturity warnings. It does not remove the original increase from available funds.
- Available funds equal all increases minus all uses, with `Decimal` accumulation.
- Maturity states are `normal`, `due_soon`, `overdue`, and `settled`; the 30-day window includes today and day 30, but excludes day 31.
- Summary additionally exposes due-soon and overdue counts for the future API summary response.

## Migration

The migration creates `biz_fund_transaction` with `DECIMAL(18,2)` amounts, the `sys_user` creator foreign key, audit timestamps, and idempotently creates `idx_fund_occurred_on` and `idx_fund_maturity_status`.

## Verification

- Passed: `D:\Investment-management\backend\.venv\Scripts\python.exe -m unittest tests.test_fund_management -v` (3 tests).
- Passed: `D:\Investment-management\backend\.venv\Scripts\python.exe -m unittest tests.test_fund_management tests.test_financial_ledger_metrics tests.test_scenic_config tests.test_hotel_scenic_config tests.test_hotel_brand_platform_parser -v` (20 tests).
- Passed: `git diff --check` for all Task 2 implementation files after staging.
- The full backend discovery suite exceeded the 60-second runner limit without producing diagnostic output; no residual Python process remained, and the scoped regression suite completed successfully.

## Integration Note

Task 3 should import `FundTransaction` in the new funds endpoint. If `python -m app.db.init_db` must also create the table on a new database without applying SQL migrations, add an explicit `FundTransaction` import to `backend/app/db/init_db.py`; the production migration already creates it.

## Fix Round 1

### Changed Behavior

- The migration now defines both `biz_fund_transaction.id` and `created_by` as `INT`, matching the repository-standard SQLAlchemy integer primary keys and the referenced `sys_user.id` foreign key.
- `FundTransactionWrite.amount` now rejects values with more than 18 total digits or more than two decimal places before they reach the `DECIMAL(18,2)` database column.

### Regression Coverage

- Added a schema test for an over-precision fractional amount (`1.001`) and an amount that exceeds 18 digits (`99999999999999999.99`).
- Added a migration-contract test that verifies integer identifier definitions and prevents reintroducing a `BIGINT` creator column.

### Verification

- Command: `D:\Investment-management\backend\.venv\Scripts\python.exe -m unittest tests.test_fund_management -v`
- Output: `Ran 5 tests ... OK`.
