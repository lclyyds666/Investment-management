# 泉城欧乐堡验证金额门票明细导入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让泉城欧乐堡上传“验证金额”格式对账文件时生成一条抖音门票台账，并按景区配置费率对整期验证金额直接计算核销金额和结算金额。

**Architecture:** 在现有门票解析器内增加仅对 `quancheng-ouleb` 生效的表头签名，将有效行的“验证金额”归一为服务商到账并在逐日快照中保留计算模式。通用计算引擎识别该模式后固定佣金为 0，先汇总整期验证金额，再分别乘核销率和结算费率，保持 API、数据库字段和前端数据结构不变。

**Tech Stack:** Python 3.13、openpyxl、Decimal、FastAPI、pytest。

## Global Constraints

- 景区 ID 必须为 `quancheng-ouleb`，平台输出必须为“抖音”。
- 两张工作表均纳入，华林园风景区和泉城欧乐堡动物王国均不得过滤。
- 仅纳入“订单状态”为“已使用”且“验证金额”为有效数字的行。
- 核销数量取“验证总数”合计；服务商到账取“验证金额”合计。
- 服务商佣金固定为 0，不从验证金额扣减。
- 景区核销金额 = 整期验证金额合计 × 景区配置核销率。
- 结算金额 = 整期验证金额合计 × 景区配置结算费率。
- 整期汇总后统一四舍五入到分，不按行或按日舍入。
- 真实文件验收值为数量 `4,064`、验证金额 `382,577.38` 元、周期 `2026-08-28` 至 `2026-09-13`。
- 使用 90%/94% 费率时，核销金额必须为 `344,319.64` 元，结算金额必须为 `359,622.74` 元。
- 不新增数据库字段、迁移或 API 字段，不改变其他景区及泉城欧乐堡标准平台文件的算法。
- 不提交或覆盖工作区中与本需求无关的用户改动。

---

### Task 1: Recognize and parse the Quancheng verification workbook

**Files:**
- Modify: `backend/app/services/ticket_ledger.py`
- Test: `backend/tests/test_ticket_ledger_ctrip_parser.py`

**Interfaces:**
- Consumes: `parse_reconciliation(content: bytes, filename: str, *, scenic_id: str, ...) -> dict` and existing header-name helpers.
- Produces: an unchanged parser result containing one platform item with `platform="抖音"`, `supplier_received`, `order_count`, period dates, and a `daily_json` snapshot carrying `calculation_mode="quancheng_verified"`.

- [ ] **Step 1: Add a generated two-sheet regression workbook**

  Add a helper that creates two sheets with different column orders and both product families:

  ```python
  @staticmethod
  def _quancheng_verification_workbook() -> bytes:
      wb = Workbook()
      first = wb.active
      first.title = "明细8.28-9.6"
      first.append([
          "订单状态", "产品名称", "验证总数", "验证金额",
          "首次入园时间", "完成时间",
      ])
      first.append([
          "已使用", "华林园风景区 手环车JY", 2, Decimal("100.01"),
          datetime(2026, 8, 28, 10, 0), datetime(2026, 8, 28, 11, 0),
      ])
      first.append([
          "未使用", "华林园风景区 手环车JY", 1, Decimal("999.00"),
          datetime(2026, 8, 29, 10, 0), None,
      ])

      second = wb.create_sheet("明细9.7-9.13")
      second.append([
          "完成时间", "验证金额", "产品名称", "订单状态",
          "首次入园时间", "验证总数",
      ])
      second.append([
          datetime(2026, 9, 13, 11, 0), Decimal("200.02"),
          "泉城欧乐堡动物王国（单景区门票产品）", "已使用",
          None, 3,
      ])
      output = BytesIO()
      wb.save(output)
      wb.close()
      return output.getvalue()
  ```

- [ ] **Step 2: Write parser assertions and verify they fail**

  Parse the generated workbook with `scenic_id="quancheng-ouleb"`, `rate_hexiao=Decimal("0.90")`, and `rate_settle=Decimal("0.94")`. Assert:

  ```python
  self.assertEqual(len(parsed["platforms"]), 1)
  item = parsed["platforms"][0]
  self.assertEqual(item["platform"], "抖音")
  self.assertEqual(item["supplier_received"], Decimal("300.03"))
  self.assertEqual(item["suggested_commission"], Decimal("0.00"))
  self.assertEqual(item["order_count"], 5)
  self.assertEqual(item["period_start"].isoformat(), "2026-08-28")
  self.assertEqual(item["period_end"].isoformat(), "2026-09-13")
  self.assertTrue(all(day["m"] == "quancheng_verified" for day in json.loads(item["daily_json"])))
  ```

  Run:

  ```powershell
  $env:PYTHONPATH='backend'
  backend\.venv\Scripts\python.exe -m pytest backend/tests/test_ticket_ledger_ctrip_parser.py -q
  ```

  Expected: the new test fails because the current platform detector does not recognize the validation headers.

- [ ] **Step 3: Add the scenic-scoped header signature**

  Define exact constants for `订单状态`, `验证总数`, `验证金额`, `首次入园时间`, and `完成时间`. Extend `_detect_platform` and `_find_platform_header` to accept `scenic_id`; after all existing platform signatures, return an internal value such as `泉城验证` only when `scenic_id == "quancheng-ouleb"` and the three required validation headers are present.

- [ ] **Step 4: Aggregate valid rows into the Douyin result**

  In `parse_reconciliation`, handle internal platform `泉城验证` before the standard branches. Reuse `platform_aggregate("抖音")`; for each row require status `已使用` and numeric validation amount, add “验证总数” through `_row_count(..., default=0)`, add the amount to `supplier_received`, update dates from first-entry then completion time, and set each daily bucket to:

  ```python
  {
      "received": Decimal("0"),
      "shishou": Decimal("0"),
      "daren": Decimal("0"),
      "tuanzhang": Decimal("0"),
      "commission_shishou": Decimal("0"),
      "commission_daren": Decimal("0"),
      "commission_tuanzhang": Decimal("0"),
      "calculation_mode": "quancheng_verified",
  }
  ```

  Do not inspect or filter “产品名称”; both product families must be included.

- [ ] **Step 5: Preserve the calculation marker through snapshots**

  Extend `_days_from_daily`, `serialize_daily`, and `_days_from_json` so the internal key `calculation_mode` serializes as compact JSON key `m` and restores unchanged. Existing snapshots without `m` must continue to parse with an empty mode.

- [ ] **Step 6: Run the focused parser suite**

  ```powershell
  $env:PYTHONPATH='backend'
  backend\.venv\Scripts\python.exe -m pytest backend/tests/test_ticket_ledger_ctrip_parser.py -q
  git diff --check -- backend/app/services/ticket_ledger.py backend/tests/test_ticket_ledger_ctrip_parser.py
  ```

  Expected: the new parser test passes and all existing platform parser tests remain green.

### Task 2: Calculate rates from the whole-period verification amount

**Files:**
- Modify: `backend/app/services/ledger_calculator.py`
- Test: `backend/tests/test_scenic_ledger_calculator.py`

**Interfaces:**
- Consumes: normalized day dictionaries with `recv` and `calculation_mode="quancheng_verified"`.
- Produces: the existing `calculate_ticket_ledger(...)` result shape with commission zero and whole-period rate calculation.

- [ ] **Step 1: Add exact business-formula tests**

  Add one realistic-value test and one rounding regression:

  ```python
  def test_quancheng_verified_amount_uses_rates_without_commission(self):
      result = ticket_ledger.calculate_ticket_ledger(
          "quancheng-ouleb",
          [{"recv": "382577.38", "calculation_mode": "quancheng_verified"}],
          rate_hexiao=Decimal("0.90"),
          rate_settle=Decimal("0.94"),
          commission_override=Decimal("999"),
          commission_rate=Decimal("0.06"),
          platform="抖音",
      )
      self.assertEqual(result["supplier_commission"], Decimal("0.00"))
      self.assertEqual(result["publisher_due"], Decimal("382577.38"))
      self.assertEqual(result["hexiao_amount"], Decimal("344319.64"))
      self.assertEqual(result["jinying_amount"], Decimal("359622.74"))
      self.assertEqual(result["service_fee"], Decimal("15303.10"))

  def test_quancheng_verified_amount_rounds_after_period_aggregation(self):
      days = [
          {"recv": "0.02", "calculation_mode": "quancheng_verified"},
          {"recv": "0.02", "calculation_mode": "quancheng_verified"},
      ]
      result = ticket_ledger.calculate_ticket_ledger(
          "quancheng-ouleb", days,
          rate_hexiao=Decimal("0.80"), rate_settle=Decimal("0.84"),
          platform="抖音",
      )
      self.assertEqual(result["hexiao_amount"], Decimal("0.03"))
      self.assertEqual(result["jinying_amount"], Decimal("0.03"))
  ```

- [ ] **Step 2: Run the calculator tests and verify the failures**

  ```powershell
  $env:PYTHONPATH='backend'
  backend\.venv\Scripts\python.exe -m pytest backend/tests/test_scenic_ledger_calculator.py -q
  ```

  Expected: the realistic test incorrectly deducts commission and the rounding test uses per-day rounding.

- [ ] **Step 3: Implement mode-scoped calculation**

  In `calculate_ticket_ledger`, define `is_quancheng_verified` only when the scenic is `quancheng-ouleb`, at least one day exists, and every day has mode `quancheng_verified`. For that case:

  - skip `_distribute_commission` regardless of platform or override;
  - sum every day’s `received` into `publisher_due`;
  - calculate `hexiao` once as `quantize_money(publisher_due * rate_hexiao)`;
  - calculate `settle` once as `quantize_money(publisher_due * rate_settle)`;
  - return `supplier_commission=0` and the existing output keys.

  Keep the current Guanquelou whole-period rule and all normal per-day rules unchanged.

- [ ] **Step 4: Prove mode and scenic isolation**

  Add assertions showing the marker does not change another scenic and an unmarked standard Quancheng Douyin snapshot still follows the existing commission/per-day path.

- [ ] **Step 5: Run both focused suites**

  ```powershell
  $env:PYTHONPATH='backend'
  backend\.venv\Scripts\python.exe -m pytest backend/tests/test_scenic_ledger_calculator.py backend/tests/test_ticket_ledger_ctrip_parser.py -q
  git diff --check -- backend/app/services/ledger_calculator.py backend/app/services/ticket_ledger.py backend/tests/test_scenic_ledger_calculator.py backend/tests/test_ticket_ledger_ctrip_parser.py
  ```

  Expected: all focused tests pass with no whitespace errors.

### Task 3: Validate the supplied workbook and regression scope

**Files:**
- Verify: `.tmp-quancheng-ticket-input.xlsx`
- Verify: `backend/app/services/ticket_ledger.py`
- Verify: `backend/app/services/ledger_calculator.py`

**Interfaces:**
- Consumes: the user-supplied workbook copied read-only into the workspace and explicit 90%/94% test rates.
- Produces: evidence for exact totals without saving a ledger row or mutating the source workbook.

- [ ] **Step 1: Parse the real workbook locally**

  Run a read-only script through the backend virtual environment that calls:

  ```python
  parsed = ticket_ledger.parse_reconciliation(
      source.read_bytes(),
      "对账明细-2026.08.28-2026.09.xlsx",
      scenic_id="quancheng-ouleb",
      rate_hexiao=Decimal("0.90"),
      rate_settle=Decimal("0.94"),
  )
  ```

  Assert one platform named “抖音”, `order_count == 4064`, `supplier_received == Decimal("382577.38")`, `def_hexiao == Decimal("344319.64")`, `def_jinying == Decimal("359622.74")`, and dates `2026-08-28`/`2026-09-13`.

- [ ] **Step 2: Run the complete affected backend test set**

  ```powershell
  $env:PYTHONPATH='backend'
  backend\.venv\Scripts\python.exe -m pytest backend/tests/test_ticket_ledger_ctrip_parser.py backend/tests/test_scenic_ledger_calculator.py backend/tests/test_portal_api.py -q
  ```

  Expected: all tests pass; unrelated dirty files are neither staged nor modified.

- [ ] **Step 3: Review the final diff**

  Confirm the only implementation files for this feature are the two services and two test modules, the formulas use caller-provided rates, and no product-name filter or hard-coded 90%/94% appears in production code.

### Task 4: Deploy and verify production behavior

**Files:**
- Deploy: `backend/app/services/ticket_ledger.py`
- Deploy: `backend/app/services/ledger_calculator.py`
- Temporary input: `/tmp/quancheng-ticket-input.xlsx`

**Interfaces:**
- Consumes: locally tested service files and the supplied workbook.
- Produces: restarted `sd-scm-backend`, healthy API, and a production-side read-only parse matching the acceptance totals.

- [ ] **Step 1: Capture production rollback files**

  On `root@39.107.52.146`, create a timestamped directory under `/opt/sd-scm/releases/` and copy the two currently deployed service files into it before replacement. Resolve and print every source and target path before copying.

- [ ] **Step 2: Upload only the tested files and workbook**

  Use `scp` to place the two Python modules in a release-specific `/tmp/quancheng-ticket-20260920/` directory and the workbook at `/tmp/quancheng-ticket-input.xlsx`. Do not upload the dirty repository, tests, local configuration, or unrelated artifacts.

- [ ] **Step 3: Install atomically and restart the backend**

  Move the validated temporary modules into `/opt/sd-scm/backend/app/services/`, preserve ownership and permissions, run a Python import/compile check, restart `sd-scm-backend`, and inspect `systemctl is-active sd-scm-backend`.

- [ ] **Step 4: Check health and production-side calculation**

  Run:

  ```bash
  curl -fsS http://127.0.0.1:8000/api/v1/health
  ```

  Then invoke `parse_reconciliation` read-only against `/tmp/quancheng-ticket-input.xlsx` using rates `0.90/0.94`. Verify platform “抖音”, count `4064`, base `382577.38`,核销 `344319.64`, and结算 `359622.74`. Do not call the save endpoint or create a production ledger row.

- [ ] **Step 5: Clean temporary deployment inputs**

  Remove only `/tmp/quancheng-ticket-input.xlsx` and the release-specific temporary upload directory after all checks pass. Keep the timestamped rollback copy under `/opt/sd-scm/releases/`.
