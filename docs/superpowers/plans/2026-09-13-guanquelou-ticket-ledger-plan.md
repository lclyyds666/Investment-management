# 鹳雀楼门票核销台账修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 `guanquelou` 多景区、多平台门票 Excel 的识别、景区过滤和抖音正数费用计算，使上传后生成正确的鹳雀楼核销台账草稿。

**Architecture:** 保留 `ticket_ledger.parse_reconciliation` 作为唯一 Excel 适配入口，在其中增加表头别名和景区筛选辅助函数；将鹳雀楼抖音的费用符号归一化到现有逐日快照字段，再继续复用 `ledger_calculator` 的逐日舍入和台账计算。接口、ORM、数据库字段与前端协议不变。

**Tech Stack:** Python 3.13, FastAPI service layer, `openpyxl` read-only parsing, `decimal.Decimal`, pytest/unittest.

## Global Constraints

- 只修复鹳雀楼门票解析与核销算法；不生成桌面 Excel 结果文件。
- 不增加数据库字段、迁移、上传接口或前端交互。
- `guanquelou` 的抖音、美团、携程、同程明细必须按景区字段过滤；缺少筛选字段必须报错。
- 鹳雀楼抖音正数费用按 `订单实收 − 软件服务费 − 达人服务费 − 撮合经纪服务费`；旧负数费用保持原有有符号规则。
- 核销、结算、服务费继续逐日四舍五入后累加；其他景区和旧逐日 JSON 保持兼容。
- 不修改工作区中与本任务无关的用户已有改动。

---

### Task 1: Add parser helpers and failing regression tests

**Files:**
- Modify: `backend/app/services/ticket_ledger.py:43-180, 260-490`
- Test: `backend/tests/test_ticket_ledger_ctrip_parser.py`

**Interfaces:**
- Consumes existing `parse_reconciliation(content, filename, scenic_id, rate_hexiao, rate_settle, commission_rate, commission_override, ticket_product)`.
- Produces the same top-level parse response and per-platform fields, with鹳雀楼-only aggregates and normalized daily commission inputs.

- [ ] **Step 1: Add failing tests for the production-shaped workbook**

  Extend `TicketLedgerCtripParserTest` with a small in-memory workbook containing four sheets:

  ```python
  def test_guanquelou_filters_mixed_scenics_and_supports_real_douyin_headers(self):
      # 抖音 header uses 订单实收 + 撮合经纪服务费 and includes 普救寺 rows.
      # 美团/携程 include both scenic names; 同程 uses 景区名称.
      parsed = ticket_ledger.parse_reconciliation(
          workbook_bytes, "鹳雀楼7.31-8.23.xlsx", scenic_id="guanquelou",
          ticket_product="鹳雀楼",
      )
      by_platform = {item["platform"]: item for item in parsed["platforms"]}
      self.assertEqual(set(by_platform), {"抖音", "美团", "携程", "同程"})
      self.assertEqual(by_platform["抖音"]["supplier_received"], Decimal("93.00"))
      self.assertEqual(by_platform["抖音"]["suggested_commission"], Decimal("3.00"))
      self.assertEqual(by_platform["美团"]["supplier_received"], Decimal("40.00"))
      self.assertEqual(by_platform["携程"]["supplier_received"], Decimal("50.00"))
      self.assertEqual(by_platform["同程"]["supplier_received"], Decimal("60.00"))
  ```

  Include assertions that non-target rows do not affect `order_count`, `positive_count`, dates, or `daily_json`.

- [ ] **Step 2: Add failing tests for missing scenic columns and signed legacy rows**

  Add tests that call `parse_reconciliation` with `scenic_id="guanquelou"` and assert:

  ```python
  with self.assertRaisesRegex(ValueError, "核销门店"):
      ticket_ledger.parse_reconciliation(missing_douyin_scenic_column, "鹳雀楼.xlsx", scenic_id="guanquelou")
  ```

  Add a second test using the historical `订单实收金额` and negative fee values; assert the existing net sum and commission behavior remain unchanged.

- [ ] **Step 3: Run the focused tests and verify they fail**

  Run: `python -m pytest backend/tests/test_ticket_ledger_ctrip_parser.py -q`

  Expected: the new鹳雀楼 tests fail because the current parser does not recognize `订单实收`, does not filter mixed scenic rows, and does not validate scenic columns.

### Task 2: Implement aliases, scenic filtering, and鹳雀楼 fee normalization

**Files:**
- Modify: `backend/app/services/ticket_ledger.py:43-180, 260-490`
- Test: `backend/tests/test_ticket_ledger_ctrip_parser.py`

**Interfaces:**
- Consumes the existing platform-specific parser branches and `_calculate_ticket_ledger` daily input shape.
- Produces a platform aggregate with `supplier_received`, counts, dates, and `daily_json` containing normalized `cs/cd/ct` values for鹳雀楼抖音.

- [ ] **Step 1: Add alias and scenic-filter helper functions**

  Define focused helpers near `_header_index`:

  ```python
  def _header_index_any(header: list, names: tuple[str, ...]) -> int:
      for name in names:
          index = _header_index(header, name)
          if index >= 0:
              return index
      return -1

  def _requires_guanquelou_filter(scenic_id: str) -> bool:
      return scenic_id == "guanquelou"

  def _matches_scenic(value, scenic_id: str, *, exact: bool = False) -> bool:
      text = str(value or "").strip()
      return text == "鹳雀楼" if exact else "鹳雀楼" in text
  ```

  Keep generic behavior unchanged when `scenic_id != "guanquelou"`.

- [ ] **Step 2: Update platform detection and branch column lookup**

  Change `COL_SHISHOU` lookup to accept `("订单实收", "订单实收金额")`; change the group-fee lookup to accept `("团长服务费", "撮合经纪服务费")`. `_detect_platform` must recognize either order-receipt header plus `核销时间`.

- [ ] **Step 3: Filter鹳雀楼 rows before all aggregation**

  In each platform branch, resolve the required scenic column when `scenic_id == "guanquelou"` and raise `ValueError("鹳雀楼明细缺少必要列：...")` when absent. Skip rows before adding amount, count, positive count, date, or daily values:

  - 抖音: `核销门店`, text contains `鹳雀楼`.
  - 美团: `产品名称`, text contains `鹳雀楼`.
  - 携程: `资源名称`, text contains `鹳雀楼`.
  - 同程: `景区名称`, exact `鹳雀楼`.

- [ ] **Step 4: Normalize鹳雀楼抖音 positive fees and preserve legacy signs**

  For each selected抖音 row, read software/daren/group fee values. If all fee values participating in the row are non-negative and the row’s `服务商服务费` is positive, compute:

  ```python
  base = shishou - software - daren - group
  commission_daren = -daren
  commission_group = -group
  ```

  Otherwise preserve the existing signed rule (`base = shishou + fee values`, commission inputs retain source signs). Never add `服务商服务费` to `base`; use it only as a consistency check/authority when present. Store the normalized commission inputs in the daily aggregate so `recompute_from_json` uses the same sign convention after a rate edit.

- [ ] **Step 5: Keep non-target platform and scenic behavior compatible**

  Do not alter the existing special rules for `zunyi-zoo`, `nanyang-wildlife`, `fuzhou-ouleb`, Ctrip `订单成本`, Meituan `消费结算`, or Tongcheng `订单金额`. Ensure ordinary old headers still run through the current paths.

- [ ] **Step 6: Run focused tests and verify they pass**

  Run: `python -m pytest backend/tests/test_ticket_ledger_ctrip_parser.py -q`

  Expected: all existing and new parser tests pass.

### Task 3: Verify production-shaped data and end-to-end recalculation

**Files:**
- Modify: `backend/tests/test_scenic_ledger_calculator.py` only if a focused calculator regression is needed.
- Test: `backend/tests/test_ticket_ledger_ctrip_parser.py`

**Interfaces:**
- Consumes the corrected parser output and existing `recompute_from_json` / `calculate_ticket_ledger` APIs.
- Produces evidence that uploaded鹳雀楼 data can be edited and recalculated without losing the corrected fee sign convention.

- [ ] **Step 1: Add a daily recalculation regression test**

  Parse a positive-fee鹳雀楼抖音 fixture, then call:

  ```python
  recalculated = ticket_ledger.recompute_from_json(
      douyin["daily_json"], Decimal("0.90"), Decimal("0.94"),
      None, Decimal("0.08"), platform="抖音", scenic_id="guanquelou",
  )
  ```

  Assert the recalculated commission uses the normalized daily fees and that publisher due, hexiao, settlement, and service fee are internally consistent.

- [ ] **Step 2: Run the production file through the parser without changing it**

  Use the existing desktop file path as an external fixture, not a repository file:

  ```powershell
  $env:PYTHONPATH="D:\Investment-management\.test-deps;D:\Investment-management\backend"
  python -c "from pathlib import Path; from app.services.ticket_ledger import parse_reconciliation; p=Path(r'C:\Users\dell\Desktop\鹳雀楼7.31-8.23.xlsx'); print(parse_reconciliation(p.read_bytes(), p.name, scenic_id='guanquelou', ticket_product='鹳雀楼')['platforms'])"
  ```

  Verify the four platform outputs contain only鹳雀楼 rows and match the design baselines within cent rounding: 抖音到账 `1,021,703.42`, 美团 `421,629.45`, 携程 `312,070.00`, 同程 `24,880.00`.

- [ ] **Step 3: Run the complete backend test suite**

  Run: `python -m pytest backend/tests -q`

  Expected: the full backend suite passes; any unrelated pre-existing failures are reported without modifying unrelated files.

- [ ] **Step 4: Review the diff and commit only task files**

  Run: `git diff --check` and `git status --short`.

  Commit only `backend/app/services/ticket_ledger.py`, the focused test file(s), and this plan if it is not already committed, using:

  ```bash
  git add backend/app/services/ticket_ledger.py backend/tests/test_ticket_ledger_ctrip_parser.py backend/tests/test_scenic_ledger_calculator.py
  git commit -m "fix: filter and calculate guanquelou ticket ledgers"
  ```

## Self-Review Checklist

- [ ] Every design requirement maps to Task 1, 2, or 3.
- [ ] No task changes database schema, frontend code, or unrelated scenic rules.
- [ ] Alias signatures and returned parser fields remain type-compatible with existing API schemas.
- [ ] Tests cover mixed景区 rows, all four platforms, missing columns, old headers, positive fees, and edited commission rates.
