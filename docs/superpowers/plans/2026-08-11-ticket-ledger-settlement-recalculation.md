# Ticket Ledger Settlement Recalculation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct Tongcheng settlement mapping and Zunyi Douyin reversal handling, make Fuzhou product `1870851250521100` commission-exempt, and safely recalculate affected production history from retained source workbooks.

**Architecture:** Keep statement-specific normalization in `ticket_ledger.py` and teach the shared calculator to consume optional commission-eligible daily aggregates with legacy fallback. Put historical comparison, manual-value protection, and balance recalculation in a dedicated repair service; expose it through an explicit dry-run-by-default CLI so deployment can validate every source file before one transactional apply.

**Tech Stack:** Python 3, FastAPI service layer, SQLAlchemy 2, MySQL, openpyxl, `decimal.Decimal`, stdlib `unittest`/`unittest.mock`, PowerShell locally, Ubuntu/systemd in production.

## Global Constraints

- Tongcheng supplier received must use `订单金额`; `商家应收` must never be a fallback amount.
- Zunyi Douyin must preserve source fee signs so refund and reversal rows add back their fees.
- Fuzhou Douyin supplier received for 2026/7/2-2026/7/25 remains exactly `1203013.49`.
- Only scenic `fuzhou-ouleb`, platform `抖音`, product ID `1870851250521100` is default-commission exempt.
- Old daily JSON without commission-eligible fields must retain existing behavior.
- Historical repair preserves detected manual supplier received, commission, writeoff, and settlement overrides.
- Historical repair is dry-run by default, validates all target source files before mutation, and applies in one database transaction.
- No frontend changes, schema migration, or new dependency.
- Use `Decimal` and the existing cent-level `ROUND_HALF_UP` rules for all money calculations.

---

## File Structure

- Modify `backend/app/services/ledger_calculator.py`: read commission-eligible daily values and distribute manual commission by eligible receipts.
- Modify `backend/app/services/ticket_ledger.py`: correct Tongcheng and Zunyi formulas, enforce Fuzhou product IDs, and serialize eligible commission aggregates.
- Create `backend/app/services/ticket_ledger_repair.py`: build validated row repair plans, protect manual values, apply calculated fields, and recompute balances.
- Create `backend/scripts/recalculate_ticket_ledgers.py`: dry-run/apply CLI and transaction boundary.
- Modify `backend/tests/test_ledger_commission_linkage.py`: calculator compatibility and exemption tests.
- Modify `backend/tests/test_ticket_ledger_ctrip_parser.py`: platform formulas, required columns, and product exemption parser tests.
- Create `backend/tests/test_ticket_ledger_repair.py`: repair planning, manual protection, missing-source, balance, and idempotence tests.
- Create `backend/tests/test_recalculate_ticket_ledgers_cli.py`: CLI dry-run/apply/rollback tests.

---

### Task 1: Commission-Eligible Daily Calculation

**Files:**
- Modify: `backend/app/services/ledger_calculator.py:53-73`
- Test: `backend/tests/test_ledger_commission_linkage.py`

**Interfaces:**
- Consumes: daily mappings with existing `shishou`/`s`, `daren`/`d`, and `tuanzhang`/`t` keys.
- Produces: `_commission_inputs(day: Mapping) -> tuple[Decimal, Decimal, Decimal]`, accepting optional long keys `commission_shishou`, `commission_daren`, `commission_tuanzhang` and compact keys `cs`, `cd`, `ct`.
- Produces: `_distribute_commission(...)` whose automatic and override distribution use eligible receipts while preserving the existing return type `tuple[list[Decimal], Decimal]`.

- [ ] **Step 1: Add a failing exemption test**

Append a test that mixes one explicitly exempt day and one eligible day:

```python
def test_ticket_commission_uses_explicit_eligible_daily_basis(self):
    daily_json = json.dumps([
        {"r": "20111", "s": "20111", "d": "0", "t": "0",
         "cs": "0", "cd": "0", "ct": "0"},
        {"r": "97", "s": "100", "d": "-2", "t": "-1",
         "cs": "100", "cd": "-2", "ct": "-1"},
    ])

    result = ticket_api.tl_svc.recompute_from_json(
        daily_json,
        Decimal("0.91"),
        Decimal("0.95"),
        None,
        Decimal("0.08"),
        "抖音",
        scenic_id="fuzhou-ouleb",
    )

    self.assertEqual(result["supplier_commission"], Decimal("5.00"))
    self.assertEqual(result["publisher_due"], Decimal("20203.00"))
```

- [ ] **Step 2: Add a failing override-distribution test**

Test the private distributor directly so the exempt day receives no share when eligible receipts exist:

```python
def test_manual_commission_is_distributed_only_by_eligible_receipts(self):
    days = [
        {"r": "20111", "s": "20111", "cs": "0", "cd": "0", "ct": "0"},
        {"r": "100", "s": "100", "cs": "100", "cd": "0", "ct": "0"},
    ]

    distributed, total = ticket_api.tl_svc._calculate_ticket_ledger.__globals__[
        "_distribute_commission"
    ](days, Decimal("10"), Decimal("0.08"))

    self.assertEqual(distributed, [Decimal("0.00"), Decimal("10.00")])
    self.assertEqual(total, Decimal("10.00"))
```

Prefer importing `app.services.ledger_calculator as calculator` at the top of the test and calling `calculator._distribute_commission(...)` rather than retaining the `__globals__` access in the final test.

- [ ] **Step 3: Run the focused tests and verify failure**

Run from `backend/`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_ledger_commission_linkage.py" -v
```

Expected: the new tests fail because automatic commission still uses `s/d/t` and override allocation still uses total `s`.

- [ ] **Step 4: Add commission-input helpers**

Implement explicit-key detection so a present zero does not fall through to legacy values:

```python
def _first_present(day: Mapping, *keys: str):
    for key in keys:
        if key in day:
            return day[key]
    return 0


def _commission_inputs(day: Mapping) -> tuple[Decimal, Decimal, Decimal]:
    return (
        _dec(_first_present(day, "commission_shishou", "cs", "shishou", "s")),
        _dec(_first_present(day, "commission_daren", "cd", "daren", "d")),
        _dec(_first_present(day, "commission_tuanzhang", "ct", "tuanzhang", "t")),
    )
```

Update `_distribute_commission` to compute each automatic amount from `_commission_inputs(day)`. Use eligible receipt as the override weight. When the eligible receipt total is zero, retain the existing equal-distribution fallback so an explicit manual override remains representable.

- [ ] **Step 5: Preserve exact manual totals after cent rounding**

The current per-day rounding can leave the distributed list a cent away from `commission_override`. After building `adjusted`, calculate the residual and add it to the last day with a positive eligible receipt, or the last day if no eligible receipt exists:

```python
residual = quantize_money(_dec(commission_override) - sum(adjusted, Decimal("0")))
if residual:
    target = next(
        (index for index in range(len(days) - 1, -1, -1)
         if _commission_inputs(days[index])[0] > 0),
        len(days) - 1,
    )
    adjusted[target] = quantize_money(adjusted[target] + residual)
```

- [ ] **Step 6: Run calculator and linkage tests**

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_ledger_commission_linkage.py" -v
```

Expected: all linkage tests pass, including legacy `_daily_json()` behavior.

- [ ] **Step 7: Commit the calculator change**

```powershell
git add -- backend/app/services/ledger_calculator.py backend/tests/test_ledger_commission_linkage.py
git commit -m "fix: support commission-exempt ticket receipts"
```

---

### Task 2: Correct Statement Parsing and Persist Eligible Basis

**Files:**
- Modify: `backend/app/services/ticket_ledger.py:43-76,129-147,276-449,512-547`
- Test: `backend/tests/test_ticket_ledger_ctrip_parser.py`

**Interfaces:**
- Consumes: Fuzhou product exemption through `(scenic_id, product_id)`.
- Produces: compact daily JSON keys `cs`, `cd`, and `ct` on newly parsed Douyin rows.
- Produces: Tongcheng `supplier_received` and daily `r` sourced only from `订单金额`.
- Produces: Zunyi Douyin received using signed `订单实收金额 + 达人服务费 + 服务商服务费`.

- [ ] **Step 1: Replace the Tongcheng fixture with both monetary columns**

Change the four-platform test fixture and assertion:

```python
tongcheng.append(["订单金额", "商家应收", "订单票数", "旅游日期"])
tongcheng.append([100, 92.12, 2, datetime(2026, 6, 10)])

self.assertEqual(by_platform["同程"]["supplier_received"], Decimal("100.00"))
```

Add a separate workbook containing only `商家应收`, `订单票数`, and `旅游日期`, and assert `ValueError` contains `订单金额`.

- [ ] **Step 2: Add the exact Zunyi reversal regression**

Build a Zunyi Douyin sheet with two rows whose signed column totals match production:

```python
douyin.append([
    "订单实收金额", "软件服务费", "达人服务费", "团长服务费",
    "服务商服务费", "核销时间",
])
douyin.append([323652, -16182.66, -1041.14, 0, -15127.42,
                datetime(2026, 4, 20, 10, 0)])
douyin.append([-154, 7.70, 0.36, 0, 7.36,
                datetime(2026, 4, 21, 10, 0)])
```

Parse with `scenic_id="zunyi-zoo"` and assert `supplier_received == Decimal("307337.16")`. This fixture must produce the old incorrect result `307321.72` before the implementation.

- [ ] **Step 3: Add Fuzhou exemption parser tests**

Create a Fuzhou Douyin workbook with a `商品ID` column:

```python
douyin.append([
    "商品ID", "订单实收金额", "软件服务费", "达人服务费",
    "团长服务费", "服务商服务费", "核销时间",
])
douyin.append([1870851250521100, 20111, 0, 0, 0, -20111,
                datetime(2026, 7, 3, 10, 0)])
douyin.append([999, 100, -5, -2, -1, -92,
                datetime(2026, 7, 3, 11, 0)])
```

Parse with `scenic_id="fuzhou-ouleb"`, `commission_rate=Decimal("0.08")`, and no commission override. Assert:

```python
self.assertEqual(douyin_result["supplier_received"], Decimal("20203.00"))
self.assertEqual(douyin_result["suggested_commission"], Decimal("5.00"))
daily = json.loads(douyin_result["daily_json"])
self.assertEqual(daily[0]["cs"], "100")
self.assertEqual(daily[0]["cd"], "-2")
self.assertEqual(daily[0]["ct"], "-1")
```

Add a Fuzhou workbook without `商品ID` and assert `ValueError` contains `福州欧乐堡抖音明细缺少必要列：商品ID`.

- [ ] **Step 4: Run parser tests and verify failure**

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_ticket_ledger_ctrip_parser.py" -v
```

Expected: Tongcheng still returns `商家应收`, Zunyi returns `307321.72`, and Fuzhou still charges the exempt product.

- [ ] **Step 5: Implement platform constants and validation**

Use distinct names and a scoped exemption set:

```python
COL_PRODUCT_ID = "商品ID"
COL_TC_ORDER_AMOUNT = "订单金额"
COL_TC_MERCHANT_RECEIVABLE = "商家应收"
_COMMISSION_EXEMPT_PRODUCTS = {
    ("fuzhou-ouleb", "1870851250521100"),
}
```

Add `_product_id(value) -> str` that converts integer-like numeric cells without a `.0` suffix. Detect Tongcheng from its stable ticket/date columns and either known monetary column, then raise if `订单金额` is absent. For Fuzhou Douyin, raise if `商品ID` is absent.

- [ ] **Step 6: Implement signed Zunyi and Tongcheng formulas**

Replace the Zunyi base calculation with:

```python
base = (
    (shishou or Decimal("0"))
    + (fee_vals[1] or Decimal("0"))
    + (fuwushang or Decimal("0"))
)
```

Remove `_fee_charge` if it has no remaining callers. In the Tongcheng branch, read only `COL_TC_ORDER_AMOUNT` into `base`.

- [ ] **Step 7: Aggregate and serialize commission-eligible values**

Initialize every daily bucket with three additional decimal fields:

```python
"commission_shishou": Decimal("0"),
"commission_daren": Decimal("0"),
"commission_tuanzhang": Decimal("0"),
```

For Douyin rows, add `shishou`, `daren`, and `tuanzhang` to these fields unless `(scenic_id, product_id)` is exempt. Update `_days_from_daily`, `serialize_daily`, and `_days_from_json` to pass `cs/cd/ct`; when JSON lacks the compact keys, omit the long eligible keys so Task 1's calculator falls back to legacy values.

- [ ] **Step 8: Run parser, calculator, and scenic regression tests**

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_ticket_ledger_ctrip_parser.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_ledger_commission_linkage.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_scenic_ledger_calculator.py" -v
```

Expected: all three files pass; the real checked-in scenic workbooks keep their previous non-target calculations.

- [ ] **Step 9: Commit parser corrections**

```powershell
git add -- backend/app/services/ticket_ledger.py backend/tests/test_ticket_ledger_ctrip_parser.py
git commit -m "fix: correct ticket statement settlement rules"
```

---

### Task 3: Build the Historical Repair Service

**Files:**
- Create: `backend/app/services/ticket_ledger_repair.py`
- Create: `backend/tests/test_ticket_ledger_repair.py`

**Interfaces:**
- Produces: `RepairPlanItem` dataclass containing the ORM row, before/after values, and protected-field flags.
- Produces: `plan_repair_row(row: TicketLedger, platform_info: Mapping) -> RepairPlanItem` for pure row decisions.
- Produces: `build_repair_plan(db: Session, upload_root: Path) -> list[RepairPlanItem]` that validates all target files without mutating rows.
- Produces: `apply_repair_plan(db: Session, items: Sequence[RepairPlanItem]) -> None` that mutates rows, flushes, and recalculates affected scenic balances without committing.
- Produces: `format_repair_plan(items: Sequence[RepairPlanItem]) -> str` with IDs, periods, platforms, changed values, and protection flags only.

- [ ] **Step 1: Write pure row-planning tests**

Construct a `TicketLedger` with old daily JSON and matching automatic values. Supply a parsed platform mapping with corrected daily JSON and assert the plan updates automatic fields:

```python
item = repair.plan_repair_row(row, {
    "platform": "抖音",
    "supplier_received": Decimal("307337.16"),
    "daily_json": new_daily_json,
    "order_count": 2,
    "positive_count": 1,
})

self.assertEqual(item.after["supplier_received"], Decimal("307337.16"))
self.assertFalse(item.protected_supplier_received)
self.assertFalse(item.protected_commission)
```

Add a Fuzhou row using the production snapshots and assert the planned values are exactly:

```python
old_calc = {
    "supplier_commission": Decimal("96151.26"),
    "publisher_due": Decimal("1106862.23"),
    "hexiao_amount": Decimal("1007244.62"),
    "jinying_amount": Decimal("1051519.13"),
    "service_fee": Decimal("44274.51"),
}
expected = {
    "supplier_received": Decimal("1203013.49"),
    "supplier_commission": Decimal("94542.38"),
    "publisher_due": Decimal("1108471.11"),
    "hexiao_amount": Decimal("1008708.69"),
    "jinying_amount": Decimal("1053047.54"),
    "service_fee": Decimal("44338.85"),
}

with patch.object(
    repair.tl_svc,
    "recompute_from_json",
    side_effect=[old_calc, expected],
):
    item = repair.plan_repair_row(row, platform_info)

self.assertEqual(
    {field: item.after[field] for field in expected},
    expected,
)
```

Set `row.daily_json` to a one-entry JSON list whose `r` equals `1203013.49`, so
the automatic supplier-received detection is exercised without requiring the
production workbook in the test repository. The parser and calculator behavior
itself is already exercised by Tasks 1 and 2; this patch isolates repair-policy
decisions.

- [ ] **Step 2: Write manual-value protection tests**

Change the row's stored supplier received, commission, writeoff, and settlement away from the old automatic snapshot. Assert those four values remain unchanged, `publisher_due` follows preserved receipt and commission, and `service_fee` equals preserved settlement minus preserved writeoff.

```python
self.assertTrue(item.protected_supplier_received)
self.assertTrue(item.protected_commission)
self.assertTrue(item.protected_hexiao)
self.assertTrue(item.protected_jinying)
self.assertEqual(item.after["service_fee"], Decimal("40.00"))
```

- [ ] **Step 3: Write orchestration validation tests**

Use `TemporaryDirectory`, one valid workbook, one missing `detail_stored`, and a fake session whose `scalars(...).all()` returns target rows. Assert `build_repair_plan` raises before changing any ORM field. Add a path traversal value such as `../outside.xlsx` and assert it is rejected.

- [ ] **Step 4: Write apply and idempotence tests**

Give `apply_repair_plan` two platform rows in one period plus a later period. Assert it updates the planned fields, calls `flush`, and assigns one shared running balance to same-period rows. Re-plan already repaired rows and assert `before == after` for all calculated values.

- [ ] **Step 5: Run repair tests and verify failure**

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_ticket_ledger_repair.py" -v
```

Expected: import fails because `ticket_ledger_repair.py` does not exist.

- [ ] **Step 6: Implement row comparison helpers**

Use a cent tolerance and explicit snapshot parsing:

```python
MONEY_TOLERANCE = Decimal("0.005")
TARGETS = frozenset({
    ("zunyi-zoo", "抖音"),
    ("zunyi-zoo", "同程"),
    ("fuzhou-ouleb", "抖音"),
})


def _money_equal(left, right) -> bool:
    return abs(Decimal(str(left or 0)) - Decimal(str(right or 0))) <= MONEY_TOLERANCE
```

Derive old automatic receipt from the sum of `r` in the stored JSON. Derive old automatic commission and downstream fields with `recompute_from_json`. Determine each protection flag before calculating the new values.

- [ ] **Step 7: Implement fully validated plan building**

Load only `TARGETS`, group by `(scenic_id, detail_stored)`, require a basename-only stored name, require the source file, parse each source once, and require exactly one matching `platform_info` per row. Build every `RepairPlanItem` before returning; do not assign any ORM attribute in this function.

- [ ] **Step 8: Implement apply and reporting**

Assign each `after` mapping to its row, flush once, reload all rows for each affected scenic in period order, and call `calculate_running_balances(..., group_by=_period_key)`. Do not call `commit` or `rollback`. Format only these values:

```text
row=77 scenic=fuzhou-ouleb platform=抖音 period=2026/7/2-2026/7/25
  supplier_commission: 96151.26 -> 94542.38
  publisher_due: 1106862.23 -> 1108471.11
  protected: none
```

- [ ] **Step 9: Run repair tests**

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_ticket_ledger_repair.py" -v
```

Expected: all repair planning, protection, validation, balance, and idempotence tests pass.

- [ ] **Step 10: Commit the repair service**

```powershell
git add -- backend/app/services/ticket_ledger_repair.py backend/tests/test_ticket_ledger_repair.py
git commit -m "feat: add ticket ledger history repair service"
```

---

### Task 4: Add the Dry-Run/Apply CLI

**Files:**
- Create: `backend/scripts/recalculate_ticket_ledgers.py`
- Create: `backend/tests/test_recalculate_ticket_ledgers_cli.py`

**Interfaces:**
- Consumes: `build_repair_plan`, `format_repair_plan`, and `apply_repair_plan` from Task 3.
- Produces: `main(argv: Sequence[str] | None = None) -> int`.
- Produces: command `python -m scripts.recalculate_ticket_ledgers` for dry-run and the same command with `--apply` for a committed transaction.

- [ ] **Step 1: Write CLI behavior tests**

Patch `SessionLocal`, `build_repair_plan`, `format_repair_plan`, and `apply_repair_plan`:

```python
def test_dry_run_does_not_apply_or_commit(self):
    result = cli.main([])
    self.assertEqual(result, 0)
    apply_repair_plan.assert_not_called()
    session.commit.assert_not_called()
    session.rollback.assert_called_once()


def test_apply_commits_once(self):
    result = cli.main(["--apply"])
    self.assertEqual(result, 0)
    apply_repair_plan.assert_called_once()
    session.commit.assert_called_once()
```

Add a failure test where plan building raises; assert rollback occurs, commit does not, and `main` returns 1.

- [ ] **Step 2: Run the CLI test and verify failure**

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_recalculate_ticket_ledgers_cli.py" -v
```

Expected: import fails because the script does not exist.

- [ ] **Step 3: Implement argument parsing and session lifecycle**

Use `argparse` with only `--apply`. Resolve uploads from `settings.UPLOAD_DIR`, build and print the plan, then:

```python
if not args.apply:
    db.rollback()
    print("DRY RUN: no database changes were committed")
    return 0

apply_repair_plan(db, items)
db.commit()
print(f"APPLIED: {len(items)} ticket ledger rows updated")
return 0
```

Catch exceptions, call `db.rollback()`, print a concise error to stderr, and return 1. Close the session in `finally`. End with `raise SystemExit(main())`.

- [ ] **Step 4: Run CLI tests**

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_recalculate_ticket_ledgers_cli.py" -v
```

Expected: dry-run, apply, and failure transaction tests pass.

- [ ] **Step 5: Exercise help without connecting to the database**

Run from `backend/`:

```powershell
.\.venv\Scripts\python.exe -m scripts.recalculate_ticket_ledgers --help
```

Expected: usage documents dry-run default and `--apply`; no DB connection is opened for `--help`.

- [ ] **Step 6: Commit the CLI**

```powershell
git add -- backend/scripts/recalculate_ticket_ledgers.py backend/tests/test_recalculate_ticket_ledgers_cli.py
git commit -m "feat: add ticket ledger recalculation command"
```

---

### Task 5: Full Regression and Production Recalculation

**Files:**
- Verify: all files changed in Tasks 1-4
- Reference: `docs/superpowers/specs/2026-08-11-ticket-ledger-settlement-recalculation-design.md`

**Interfaces:**
- Consumes: the parser, calculator, repair service, and CLI from Tasks 1-4.
- Produces: tested local code, deployed backend files, a database backup, dry-run evidence, applied historical corrections, and production query evidence.

- [ ] **Step 1: Run the complete backend test suite**

Run from `backend/`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Expected: all tests pass.

- [ ] **Step 2: Run static change checks**

Run from the repository root:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors; only intended implementation files plus unrelated pre-existing workspace files are shown.

- [ ] **Step 3: Review the implementation against production acceptance values**

Confirm tests or a local fixture assert all of these exact values:

```text
Zunyi Douyin 2026/4/17-2026/4/26 supplier_received = 307337.16
Fuzhou Douyin 2026/7/2-2026/7/25 supplier_received = 1203013.49
Fuzhou supplier_commission = 94542.38
Fuzhou publisher_due = 1108471.11
Fuzhou hexiao_amount = 1008708.69
Fuzhou jinying_amount = 1053047.54
Fuzhou service_fee = 44338.85
Tongcheng supplier_received = 8666.00, 1589.00, 1161.00
```

- [ ] **Step 4: Commit any final test-only corrections**

If Step 1 required a focused correction, stage only its files and commit:

```powershell
git add -- backend/app/services backend/scripts backend/tests
git commit -m "test: cover ticket ledger production recalculation"
```

If no files changed after the Task 4 commit, skip this commit.

- [ ] **Step 5: Create a production database backup**

Run from the local repository root:

```powershell
ssh root@39.107.52.146 "cd /opt/sd-scm/backend && set -a && . ./.env && ts=`$(date +%Y%m%d_%H%M%S) && mkdir -p /opt/sd-scm/backups && mysqldump --single-transaction -h \"`$DB_HOST\" -P \"`$DB_PORT\" -u \"`$DB_USER\" -p\"`$DB_PASSWORD\" \"`$DB_NAME\" biz_ticket_ledger > /opt/sd-scm/backups/ticket_ledger_formula_`$ts.sql && echo /opt/sd-scm/backups/ticket_ledger_formula_`$ts.sql"
```

Expected: the remote command prints one non-empty backup path. Verify it with `ssh root@39.107.52.146 "ls -lh /opt/sd-scm/backups/ticket_ledger_formula_*.sql"`.

- [ ] **Step 6: Package and deploy only backend repair files**

Run from the repository root:

```powershell
tar -czf .tmp-ticket-ledger-formula-fix.tgz -C backend app/services/ledger_calculator.py app/services/ticket_ledger.py app/services/ticket_ledger_repair.py scripts/recalculate_ticket_ledgers.py
scp .tmp-ticket-ledger-formula-fix.tgz root@39.107.52.146:/tmp/
ssh root@39.107.52.146 "tar -xzf /tmp/.tmp-ticket-ledger-formula-fix.tgz -C /opt/sd-scm/backend && chown -R www-data:www-data /opt/sd-scm/backend/app /opt/sd-scm/backend/scripts"
```

Expected: files land under `/opt/sd-scm/backend` with `www-data` ownership.

- [ ] **Step 7: Run production dry-run before restart or mutation**

```powershell
ssh root@39.107.52.146 "cd /opt/sd-scm/backend && sudo -u www-data PYTHONPATH=. .venv/bin/python -m scripts.recalculate_ticket_ledgers"
```

Expected: exit 0, `DRY RUN`, all target rows listed, no missing source or platform errors, and the acceptance values from Step 3 appear.

- [ ] **Step 8: Apply history in one transaction**

```powershell
ssh root@39.107.52.146 "cd /opt/sd-scm/backend && sudo -u www-data PYTHONPATH=. .venv/bin/python -m scripts.recalculate_ticket_ledgers --apply"
```

Expected: exit 0 and `APPLIED` with the target-row count; no partial-error output.

- [ ] **Step 9: Restart and health-check the backend**

```powershell
ssh root@39.107.52.146 "systemctl restart sd-scm-backend && systemctl is-active sd-scm-backend"
curl.exe -fsS http://39.107.52.146/api/v1/health
```

Expected: systemd reports `active`; health endpoint returns success.

- [ ] **Step 10: Query production acceptance rows**

Use the application environment to query only aggregate ledger fields:

```powershell
ssh root@39.107.52.146 "cd /opt/sd-scm/backend && set -a && . ./.env && mysql --batch --raw --skip-column-names -h \"`$DB_HOST\" -P \"`$DB_PORT\" -u \"`$DB_USER\" -p\"`$DB_PASSWORD\" \"`$DB_NAME\" -e \"SELECT scenic_id,platform,check_date_text,supplier_received,supplier_commission,publisher_due,hexiao_amount,jinying_amount,service_fee FROM biz_ticket_ledger WHERE (scenic_id='zunyi-zoo' AND platform IN ('抖音','同程')) OR (scenic_id='fuzhou-ouleb' AND platform='抖音') ORDER BY scenic_id,period_start,platform\""
```

Expected: the rows match Step 3, including the three Tongcheng order amounts and unchanged Fuzhou supplier received.

- [ ] **Step 11: Re-run dry-run to prove idempotence**

```powershell
ssh root@39.107.52.146 "cd /opt/sd-scm/backend && sudo -u www-data PYTHONPATH=. .venv/bin/python -m scripts.recalculate_ticket_ledgers"
```

Expected: every calculated before/after value is equal and no further database change is proposed.

- [ ] **Step 12: Remove only the local and remote deployment archive**

Resolve both targets explicitly, then remove these two known archives:

```powershell
Remove-Item -LiteralPath 'D:\Investment-management\.tmp-ticket-ledger-formula-fix.tgz' -Force
ssh root@39.107.52.146 "rm -f /tmp/.tmp-ticket-ledger-formula-fix.tgz"
```

Expected: archives are removed; the database backup is retained.
