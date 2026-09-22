# 泉城采购金额算法与南阳同程接入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将泉城欧乐堡新上传门票明细改为按采购金额计算，并验证南阳同程复用遵义同程规则，同时把生产泉城门票配置更新为 91%/96%。

**Architecture:** 泉城解析器为新文件输出独立的 `quancheng_purchase` 快照标记，计算引擎据此执行“采购金额×核销率”和“采购金额÷核销率×结算费率”；旧 `quancheng_verified` 快照继续使用旧语义。南阳同程继续走现有通用同程解析器，只增加景区级回归覆盖；生产配置通过 SQLAlchemy 会话只更新门票字段。

**Tech Stack:** Python 3.13、FastAPI、SQLAlchemy、openpyxl、Decimal、pytest、systemd。

## Global Constraints

- 泉城景区 ID 为 `quancheng-ouleb`，平台输出为“抖音”。
- 三张工作表全部纳入，华林园风景区和泉城欧乐堡动物王国均不得过滤。
- 仅纳入“订单状态”为“已使用”的行；核销数量取“验证总数”合计。
- 门票服务商到账和计算基数取“采购金额”合计，服务商佣金固定为 0。
- 景区核销金额 = 采购金额合计 × 核销率。
- 结算金额 = 采购金额合计 ÷ 核销率 × 结算费率。
- 金额按整期合计后统一四舍五入到分；核销率为 0 时必须明确失败。
- 新文件验收值：数量 `4,944`、采购金额 `442,361.92`、核销 `402,549.35`、结算 `466,667.52`、服务费 `64,118.17`、周期 `2026-08-28` 至 `2026-09-20`。
- 新快照使用 `quancheng_purchase`；旧 `quancheng_verified` 语义不得改变。
- 南阳同程与遵义同程都以订单金额为基数，并沿用相同日期聚合与舍入方式。
- 南阳抖音和携程算法不得改变，不新增南阳美团规则。
- 生产只更新 `quancheng-ouleb` 的门票费率为 `0.91/0.96`，不得修改酒店配置或自动重算已有台账。
- 主工作区四个门票目标文件包含此前已部署但未提交的鹳雀楼与泉城改动；不得用旧分支文件整文件覆盖。
- 不提交、覆盖或部署与本需求无关的用户改动。

---

### Task 1: Parse Quancheng purchase amounts safely

**Files:**
- Modify: `backend/app/services/ticket_ledger.py`
- Test: `backend/tests/test_ticket_ledger_ctrip_parser.py`

**Interfaces:**
- Consumes: `parse_reconciliation(content: bytes, filename: str, *, scenic_id: str, rate_hexiao: Decimal, rate_settle: Decimal, commission_rate: Decimal, commission_override, ticket_product: str) -> dict` and the existing Quancheng header signature.
- Produces: one “抖音” platform item whose `supplier_received` is the purchase total and whose `daily_json` entries carry `m="quancheng_purchase"`.

- [ ] **Step 1: Replace the generated Quancheng fixture with purchase amounts**

  Give both reordered sheets a `采购金额` column and make verification amounts deliberately different from purchase amounts:

  ```python
  first.append([
      "已使用", "华林园风景区 手环车JY", 2,
      Decimal("100.01"), Decimal("90.01"),
      datetime(2026, 8, 28, 10, 0), datetime(2026, 8, 28, 11, 0),
  ])
  second.append([
      datetime(2026, 9, 20, 11, 0), Decimal("200.02"), Decimal("180.02"),
      "泉城欧乐堡动物王国（单景区门票产品）", "已使用", None, 3,
  ])
  ```

  Assert the parser returns purchase total `270.03`, order count `5`, zero commission, dates `2026-08-28`/`2026-09-20`, and JSON days whose `m` is `quancheng_purchase` and whose `r` values sum to `270.03`.

- [ ] **Step 2: Add strict missing-purchase regressions**

  Add two tests:

  ```python
  with self.assertRaisesRegex(ValueError, "泉城欧乐堡门票明细缺少必要列：采购金额"):
      ticket_ledger.parse_reconciliation(workbook_without_purchase, scenic_id="quancheng-ouleb")

  with self.assertRaisesRegex(ValueError, "采购金额为空或无效"):
      ticket_ledger.parse_reconciliation(workbook_with_used_row_missing_purchase, scenic_id="quancheng-ouleb")
  ```

  A numeric zero remains valid; only absent, blank, or nonnumeric values fail.

- [ ] **Step 3: Run the parser tests and verify current failures**

  ```powershell
  $env:PYTHONPATH='backend;.test-deps'
  backend\.venv\Scripts\python.exe -m pytest backend/tests/test_ticket_ledger_ctrip_parser.py -q
  ```

  Expected: purchase-total and marker assertions fail because the current parser still stores verification amounts; validation tests fail because purchase data is not required.

- [ ] **Step 4: Implement the purchase parser**

  Add `COL_QC_PURCHASE = "采购金额"`. Keep the existing scenic-scoped signature so an old malformed file is recognized, then require `COL_QC_PURCHASE` inside the `泉城验证` branch. For every “已使用” row:

  ```python
  purchase = _num(raw[i_purchase]) if 0 <= i_purchase < len(raw) else None
  if purchase is None:
      raise ValueError(
          f"泉城欧乐堡门票明细第 {row_number} 行采购金额为空或无效"
      )
  aggregate["supplier_received"] += purchase
  dd["received"] += purchase
  dd["calculation_mode"] = "quancheng_purchase"
  ```

  Keep count, product inclusion and date behavior unchanged. Preserve `_days_from_json` compatibility with existing `quancheng_verified` values.

- [ ] **Step 5: Run focused parser tests and diff checks**

  ```powershell
  $env:PYTHONPATH='backend;.test-deps'
  backend\.venv\Scripts\python.exe -m pytest backend/tests/test_ticket_ledger_ctrip_parser.py -q
  git diff --check -- backend/app/services/ticket_ledger.py backend/tests/test_ticket_ledger_ctrip_parser.py
  ```

  Expected: all parser tests pass; no other platform result changes.

### Task 2: Calculate purchase formulas and preserve edit semantics

**Files:**
- Modify: `backend/app/services/ledger_calculator.py`
- Modify: `backend/app/services/ticket_ledger.py`
- Modify: `backend/app/api/v1/endpoints/ticket_ledger.py`
- Test: `backend/tests/test_scenic_ledger_calculator.py`
- Test: `backend/tests/test_ledger_commission_linkage.py`

**Interfaces:**
- Consumes: daily entries with `calculation_mode="quancheng_purchase"` or legacy `quancheng_verified`.
- Produces: existing calculation result keys plus helpers `calculation_mode_from_json(daily_json: str) -> str` and `single_amount_daily_json(amount: Decimal, mode: str) -> str` for edit recalculation.

- [ ] **Step 1: Add exact calculator tests**

  ```python
  result = ticket_ledger.calculate_ticket_ledger(
      "quancheng-ouleb",
      [{"recv": "442361.92", "calculation_mode": "quancheng_purchase"}],
      rate_hexiao=Decimal("0.91"),
      rate_settle=Decimal("0.96"),
      commission_override=Decimal("999"),
      platform="抖音",
  )
  self.assertEqual(result["supplier_commission"], Decimal("0.00"))
  self.assertEqual(result["publisher_due"], Decimal("442361.92"))
  self.assertEqual(result["hexiao_amount"], Decimal("402549.35"))
  self.assertEqual(result["jinying_amount"], Decimal("466667.52"))
  self.assertEqual(result["service_fee"], Decimal("64118.17"))
  ```

  Add `assertRaisesRegex(ValueError, "核销率必须大于 0")` for purchase mode with a zero rate. Keep a legacy test proving `quancheng_verified` at 91%/96% returns `base×0.91` and `base×0.96`.

- [ ] **Step 2: Add manual-received edit regression**

  Build a `TicketLedger` row scoped to `quancheng-ouleb` with:

  ```python
  daily_json = json.dumps([{"r": "442361.92", "m": "quancheng_purchase"}])
  supplier_received = Decimal("442361.92")
  supplier_commission = Decimal("0")
  rate_hexiao = Decimal("0.91")
  rate_settle = Decimal("0.96")
  ```

  Update `supplier_received` to `500000` and assert preview/update both produce核销 `455000.00`,结算 `527472.53`, commission `0`, and a retained JSON marker with total `r=500000`. Then change only settlement rate to `0.95` and assert结算 `521978.02`, proving future edits still use the purchase formula.

- [ ] **Step 3: Run calculator and linkage tests to verify failures**

  ```powershell
  $env:PYTHONPATH='backend;.test-deps'
  backend\.venv\Scripts\python.exe -m pytest backend/tests/test_scenic_ledger_calculator.py backend/tests/test_ledger_commission_linkage.py -q
  ```

- [ ] **Step 4: Implement the dedicated calculation branch**

  In `calculate_ticket_ledger`, distinguish modes without changing legacy behavior:

  ```python
  mode = _uniform_calculation_mode(days)
  if sid == "quancheng-ouleb" and mode == "quancheng_purchase":
      if not rate_hexiao:
          raise ValueError("泉城欧乐堡门票核销率必须大于 0")
      publisher_due = quantize_money(sum(received_values, Decimal("0")))
      hexiao = quantize_money(publisher_due * rate_hexiao)
      settle = quantize_money(publisher_due / rate_hexiao * rate_settle)
      return {
          "scenic_id": sid,
          "supplier_commission": Decimal("0.00"),
          "publisher_due": publisher_due,
          "hexiao_amount": hexiao,
          "service_fee": quantize_money(settle - hexiao),
          "jinying_amount": settle,
      }
  ```

  Leave the existing `quancheng_verified` branch as `publisher_due×rate_hexiao` and `publisher_due×rate_settle`. Mixed or absent modes continue down the existing generic path.

- [ ] **Step 5: Preserve purchase mode after manual base edits**

  Implement `calculation_mode_from_json` by parsing `_days_from_json` and returning a mode only when all nonempty days share it. Implement `single_amount_daily_json` using the existing compact keys (`r`, `s`, `d`, `t`, `cs`, `cd`, `ct`, `m`).

  In `_effective_ticket_calculation`, before calculating `snapshot_calc`:

  ```python
  mode = tl_svc.calculation_mode_from_json(daily_json)
  if received_changed and mode == "quancheng_purchase":
      daily_json = tl_svc.single_amount_daily_json(
          supplier_received, "quancheng_purchase"
      )
  ```

  The recalculated snapshot now matches the edited amount and is persisted by `update_row`, so later rate edits retain the formula.

- [ ] **Step 6: Run focused tests and diff checks**

  ```powershell
  $env:PYTHONPATH='backend;.test-deps'
  backend\.venv\Scripts\python.exe -m pytest backend/tests/test_scenic_ledger_calculator.py backend/tests/test_ledger_commission_linkage.py backend/tests/test_ticket_ledger_ctrip_parser.py -q
  git diff --check -- backend/app/services/ledger_calculator.py backend/app/services/ticket_ledger.py backend/app/api/v1/endpoints/ticket_ledger.py backend/tests/test_scenic_ledger_calculator.py backend/tests/test_ledger_commission_linkage.py
  ```

### Task 3: Prove Nanyang Tongcheng reuses Zunyi rules

**Files:**
- Test: `backend/tests/test_ticket_ledger_ctrip_parser.py`

**Interfaces:**
- Consumes: existing generic Tongcheng parser and Nanyang-specific Douyin rule.
- Produces: regression evidence only; production parser code should not change unless the test reveals a real incompatibility.

- [ ] **Step 1: Add a Nanyang three-platform workbook test**

  Generate a workbook containing:

  ```python
  # Douyin: Nanyang keeps order-received base.
  ["订单实收金额", "软件服务费", "达人服务费", "团长服务费", "核销时间"]
  [100, -5, -2, -1, datetime(2026, 9, 1)]

  # Ctrip: unchanged order-cost flow.
  ["结算价金额", "流水类型", "使用份数", "出发时间"]
  [50, "订单成本", 1, datetime(2026, 9, 2)]

  # Tongcheng: same order-amount rule as Zunyi.
  ["订单金额", "商家应收", "订单票数", "旅游日期"]
  [60, 55, 2, datetime(2026, 9, 3)]
  ```

  Parse with `scenic_id="nanyang-wildlife"`, rates `0.80/0.85`, commission rate/default `0`, and assert platforms `抖音/携程/同程` with bases `100/50/60`,核销 `80/40/48`,结算 `85/42.50/51`, and counts `1/1/2`.

- [ ] **Step 2: Compare Nanyang and Zunyi Tongcheng output**

  Parse the same Tongcheng-only sheet once as `nanyang-wildlife` and once as `zunyi-zoo` with identical rates. Assert `supplier_received`, `def_hexiao`, `def_jinying`, `order_count`, period dates and serialized daily totals match exactly.

- [ ] **Step 3: Run the parser suite**

  ```powershell
  $env:PYTHONPATH='backend;.test-deps'
  backend\.venv\Scripts\python.exe -m pytest backend/tests/test_ticket_ledger_ctrip_parser.py -q
  ```

  Expected: tests pass without production changes. If a failure reveals a parser incompatibility, make the smallest scenic-scoped correction and rerun all Task 1–3 focused suites.

### Task 4: Validate the real workbook, deploy, and update configuration

**Files:**
- Verify input: `C:/Users/dell/Desktop/对账明细-2026.08.28-2026.09.20(1).xlsx`
- Deploy only changed backend service/API files.
- Production configuration row: `biz_scenic_config.scenic_id = 'quancheng-ouleb'`.

**Interfaces:**
- Consumes: tested parser/calculator code and production SQLAlchemy `SessionLocal`.
- Produces: healthy backend, exact production-side read-only parse, ticket rates `0.9100/0.9600`, unchanged hotel fields, and no new ledger rows.

- [ ] **Step 1: Validate the real workbook locally**

  Call `parse_reconciliation` with explicit rates `0.91/0.96` and assert:

  ```python
  assert item["platform"] == "抖音"
  assert item["order_count"] == 4944
  assert item["supplier_received"] == Decimal("442361.92")
  assert item["def_hexiao"] == Decimal("402549.35")
  assert item["def_jinying"] == Decimal("466667.52")
  assert item["def_service_fee"] == Decimal("64118.17")
  assert item["period_start"].isoformat() == "2026-08-28"
  assert item["period_end"].isoformat() == "2026-09-20"
  ```

- [ ] **Step 2: Run all affected tests**

  ```powershell
  $env:PYTHONPATH='backend;.test-deps'
  backend\.venv\Scripts\python.exe -m pytest backend/tests/test_ticket_ledger_ctrip_parser.py backend/tests/test_scenic_ledger_calculator.py backend/tests/test_ledger_commission_linkage.py backend/tests/test_portal_api.py -q
  ```

  Record unrelated pre-existing collection failures separately; do not modify unrelated permissions or legal modules.

- [ ] **Step 3: Integrate without overwriting dirty deployed work**

  Compare each implementation file against the main worktree. Apply only the reviewed purchase-mode and edit-linkage hunks to the main worktree with `apply_patch`; preserve Guanquelou tuple filters, Guanquelou whole-period rounding and all unrelated user edits. Rerun Steps 1–2 against the integrated main worktree before packaging.

- [ ] **Step 4: Back up and deploy changed code**

  On `root@39.107.52.146`, print source/target paths and copy every replaced production file into `/opt/sd-scm/releases/quancheng-purchase-20260921-v1/`. Upload only reviewed files into `/tmp/quancheng-purchase-20260921-v1/`, run the production virtual environment’s `py_compile`, install via `.new` files plus atomic `mv`, restart `sd-scm-backend`, and require both:

  ```bash
  systemctl is-active sd-scm-backend
  curl -fsS http://127.0.0.1:8000/api/v1/health
  ```

- [ ] **Step 5: Run production-side read-only workbook acceptance**

  Upload the workbook temporarily, call `parse_reconciliation` from `/opt/sd-scm/backend` with `PYTHONPATH=/opt/sd-scm/backend` and explicit `0.91/0.96`, and assert all eight values from Step 1. Do not call the save endpoint.

- [ ] **Step 6: Update only the production ticket rates**

  Run a reviewed temporary Python script through the production virtual environment:

  ```python
  from decimal import Decimal
  from app.db.session import SessionLocal
  from app.models.scenic_config import ScenicConfig

  with SessionLocal() as db:
      row = db.get(ScenicConfig, "quancheng-ouleb")
      if row is None:
          raise RuntimeError("泉城欧乐堡景区配置不存在")
      before = (
          row.ticket_rate_hexiao, row.ticket_rate_settle,
          row.hotel_rate_hexiao, row.hotel_rate_settle,
      )
      row.ticket_rate_hexiao = Decimal("0.91")
      row.ticket_rate_settle = Decimal("0.96")
      db.commit()
      db.refresh(row)
      after = (
          row.ticket_rate_hexiao, row.ticket_rate_settle,
          row.hotel_rate_hexiao, row.hotel_rate_settle,
      )
      print("BEFORE", before)
      print("AFTER", after)
      assert after[:2] == (Decimal("0.9100"), Decimal("0.9600"))
      assert after[2:] == before[2:]
  ```

  Read the effective configuration again after the transaction and assert the ticket rates are `0.9100/0.9600`. Do not issue any `UPDATE` against `biz_ticket_ledger`.

- [ ] **Step 7: Clean temporary inputs and retain rollback**

  Remove only `/tmp/quancheng-purchase-20260921-v1/`, the temporary workbook and configuration script after all checks pass. Keep `/opt/sd-scm/releases/quancheng-purchase-20260921-v1/` for rollback and report that exact path.
