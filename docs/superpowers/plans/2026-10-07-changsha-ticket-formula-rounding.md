# 长沙动趣门票台账公式调整 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将长沙动趣门票台账改为美团只取应付金额、携程取结算价金额，并让抖音服务商佣金按每条订单实收先四舍五入到分后汇总。

**Architecture:** 公共纯函数计算器负责长沙抖音逐行佣金舍入及旧快照回退；Excel 解析器负责长沙美团基数选择、必要列校验，以及把抖音每条订单实收写入逐日快照 `co`。现有外部 API 和数据库结构不变，旧 `daily_json` 没有 `co` 时继续使用历史整期算法。

**Tech Stack:** Python 3.13、`Decimal`/`ROUND_HALF_UP`、openpyxl、标准库 `unittest`、JSON 逐日快照。

## Global Constraints

- 业务设计以 `docs/superpowers/specs/2026-10-07-changsha-ticket-formula-rounding-design.md` 为唯一口径。
- 仅修改 `scenic_id = "changsha-dongqu"` 的门票算法；不得改变酒店台账、外部 API schema、数据库结构或景区配置费率。
- 美团只统计“消费结算”，服务商到账只取应付金额；技术服务费存在时忽略，缺失时不报错。
- 携程只统计“订单成本”，服务商到账取结算价金额。
- 抖音每条有效明细先执行 `quantize_money(订单实收 × 佣金率)`，再汇总达人、团长和平台撮合的原始带符号费用。
- 正常负费用降低佣金，正数退款或冲正费用反向增加佣金；不得对费用取绝对值。
- 手工服务商佣金继续覆盖自动佣金；出版应得、核销、结算和服务费继续使用长沙整期计算路径。
- 新快照用 `commission_order_rows` 表示内存字段、`co` 表示 JSON 字段；旧快照缺少或无法识别 `co` 时回退到现有整期算法。
- 已有旧台账不做数据库迁移；要获得逐行舍入结果必须重新上传原始文件。
- 使用 `C:\Users\dell\Desktop\长沙动趣9.11-9.20(1).xlsx` 只读验收，不复制进仓库、不提交 Git。
- 实施继续在 `fix/changsha-ticket-formula-rounding` 隔离工作树进行，不覆盖主工作区现有未提交改动。

## File Structure

- `backend/app/services/ledger_calculator.py`：纯计算边界；读取逐行订单实收，执行逐行佣金舍入，并为旧快照保留整期回退。
- `backend/app/services/ticket_ledger.py`：Excel 平台识别、长沙美团基数、必要列校验、`commission_order_rows` 聚合和 `co` 序列化/反序列化。
- `backend/tests/test_scenic_ledger_calculator.py`：锁定逐行舍入、带符号费用、手工覆盖和旧快照结果。
- `backend/tests/test_ticket_ledger_ctrip_parser.py`：锁定三平台解析、快照往返、缺列错误以及遵义美团回归。

---

### Task 1: 长沙抖音逐行佣金纯函数

**Files:**
- Modify: `backend/app/services/ledger_calculator.py:52-125`
- Test: `backend/tests/test_scenic_ledger_calculator.py:12-77`

**Interfaces:**
- Consumes: `days: list[dict]`，每个新式长沙抖音日快照包含 `commission_order_rows: list[str | Decimal]` 或紧凑键 `co`。
- Produces: `_commission_order_amounts(days: list[dict]) -> list[Decimal] | None`；返回 `None` 表示旧快照，应走现有整期算法。
- Produces: `_calculate_changsha_ticket_period(...) -> dict` 保持现有返回键 `supplier_commission`、`publisher_due`、`hexiao_amount`、`service_fee`、`jinying_amount`。

- [ ] **Step 1: 写入逐行舍入和费用符号测试**

在 `ScenicLedgerCalculatorTest` 增加：

```python
def test_changsha_douyin_rounds_order_commission_per_source_row(self):
    days = [
        {
            "r": "0.02", "cs": "0.03", "cd": "-0.01",
            "ct": "0", "pf": "0", "commission_order_rows": ["0.03"],
        },
        {
            "r": "0.04", "cs": "0.03", "cd": "0.01",
            "ct": "0", "pf": "0", "commission_order_rows": ["0.03"],
        },
    ]

    result = ticket_ledger.calculate_ticket_ledger(
        "changsha-dongqu", days,
        rate_hexiao=Decimal("0.93"),
        rate_settle=Decimal("0.96"),
        commission_rate=Decimal("0.18"),
        platform="抖音",
    )

    self.assertEqual(result["supplier_commission"], Decimal("0.02"))
    self.assertEqual(result["publisher_due"], Decimal("0.04"))

def test_changsha_douyin_keeps_signed_fee_direction_with_row_rounding(self):
    days = [
        {
            "r": "98", "cs": "100", "cd": "-2", "ct": "0", "pf": "0",
            "commission_order_rows": ["100"],
        },
        {
            "r": "101", "cs": "100", "cd": "1", "ct": "0", "pf": "0",
            "commission_order_rows": ["100"],
        },
    ]

    result = ticket_ledger.calculate_ticket_ledger(
        "changsha-dongqu", days,
        commission_rate=Decimal("0.18"), platform="抖音",
    )

    self.assertEqual(result["supplier_commission"], Decimal("35.00"))
    self.assertEqual(result["publisher_due"], Decimal("164.00"))
```

同时保留现有 `test_changsha_douyin_aggregates_commission_and_rates_for_period`，它没有逐行列表，必须继续证明旧快照结果为 `9081.08`。

- [ ] **Step 2: 运行新测试确认失败**

从 `backend/` 运行：

```powershell
$env:PYTHONPATH=".;D:/Investment-management/.test-deps"
python -m unittest tests.test_scenic_ledger_calculator.ScenicLedgerCalculatorTest.test_changsha_douyin_rounds_order_commission_per_source_row tests.test_scenic_ledger_calculator.ScenicLedgerCalculatorTest.test_changsha_douyin_keeps_signed_fee_direction_with_row_rounding tests.test_scenic_ledger_calculator.ScenicLedgerCalculatorTest.test_changsha_douyin_aggregates_commission_and_rates_for_period -v
```

Expected: 第一项失败，当前整期算法返回佣金 `0.01` 而不是 `0.02`；旧快照测试继续通过。

- [ ] **Step 3: 实现逐行输入识别和兼容回退**

在 `_commission_inputs` 后增加：

```python
def _commission_order_amounts(days: list[dict]) -> list[Decimal] | None:
    amounts: list[Decimal] = []
    for day in days:
        raw = day.get("commission_order_rows", day.get("co"))
        if not isinstance(raw, list):
            return None
        amounts.extend(_dec(value) for value in raw)
    return amounts
```

在 `_calculate_changsha_ticket_period` 的抖音分支中保留现有 `shishou`、达人、团长和平台撮合汇总，并将自动佣金改为：

```python
rate = commission_rate or Decimal("0")
order_amounts = _commission_order_amounts(days)
if order_amounts is None:
    automatic = quantize_money(
        shishou * rate + daren + tuanzhang + platform_fee
    )
else:
    rounded_order_commission = sum(
        (quantize_money(amount * rate) for amount in order_amounts),
        Decimal("0"),
    )
    automatic = quantize_money(
        rounded_order_commission + daren + tuanzhang + platform_fee
    )
```

不要改动手工佣金覆盖及整期出版应得、核销、结算、服务费计算。

- [ ] **Step 4: 运行计算器回归测试**

```powershell
$env:PYTHONPATH=".;D:/Investment-management/.test-deps"
python -m unittest tests.test_scenic_ledger_calculator -v
```

Expected: `test_changsha_douyin_rounds_order_commission_per_source_row` 返回 `0.02`；旧长沙结果仍为 `9081.08`；文件全部通过。

- [ ] **Step 5: 提交纯函数改动**

```powershell
git add -- backend/app/services/ledger_calculator.py backend/tests/test_scenic_ledger_calculator.py
git commit -m "fix: round Changsha commission per order"
```

---

### Task 2: 长沙三平台解析与逐行快照

**Files:**
- Modify: `backend/app/services/ticket_ledger.py:88-94,192-233,365-638,742-800`
- Test: `backend/tests/test_ticket_ledger_ctrip_parser.py:51-90,369-435`

**Interfaces:**
- Consumes: Task 1 的 `commission_order_rows`/`co` 和 `_calculate_changsha_ticket_period`。
- Produces: 长沙抖音 `daily_json` 每日对象含 `co: list[str]`；`_days_from_json` 恢复为 `commission_order_rows`。
- Produces: `_detect_platform(header: list, scenic_id: str = "legacy") -> str | None` 和 `_find_platform_header(rows_iter, scenic_id: str = "legacy") -> tuple[str, list] | None`，只为长沙缺少主金额列时提供可诊断的识别回退。
- Produces: 长沙美团服务商到账仅为消费结算应付金额；遵义美团仍为应付金额加技术服务费。

- [ ] **Step 1: 扩展长沙合成工作簿夹具**

将 `_changsha_workbook` 签名改为：

```python
def _changsha_workbook(
    platform_fee_header="平台撮合服务费",
    omitted_header=None,
    include_meituan_tech_fee=True,
) -> bytes:
```

构造美团和携程表头时同样过滤 `omitted_header`。美团行通过表头字典投影，确保 `include_meituan_tech_fee=False` 时完全不写“技术服务费”列，而应付金额仍为 `100`。抖音两行保持 `100` 与 `-20`，携程有效订单成本保持 `50`。

- [ ] **Step 2: 写入快照、费率重算和三平台基数失败测试**

在现有长沙测试中增加以下断言并更新美团期望：

```python
snapshot = json.loads(douyin["daily_json"])
self.assertEqual([day["co"] for day in snapshot], [["100"], ["-20"]])

recomputed = ticket_ledger.recompute_from_json(
    douyin["daily_json"],
    Decimal("0.93"), Decimal("0.96"), None, Decimal("0.06665"),
    "抖音", "changsha-dongqu",
)
self.assertEqual(recomputed["supplier_commission"], Decimal("-0.66"))
```

将美团/携程断言改为：

```python
self.assertEqual(by_platform["美团"]["supplier_received"], Decimal("100.00"))
self.assertEqual(by_platform["美团"]["def_hexiao"], Decimal("93.00"))
self.assertEqual(by_platform["美团"]["def_jinying"], Decimal("96.00"))
self.assertEqual(by_platform["携程"]["supplier_received"], Decimal("50.00"))
self.assertEqual(by_platform["携程"]["def_hexiao"], Decimal("46.50"))
self.assertEqual(by_platform["携程"]["def_jinying"], Decimal("48.00"))
```

增加技术服务费可选和必要金额列错误测试：

```python
def test_changsha_meituan_does_not_require_or_include_technical_fee(self):
    parsed = ticket_ledger.parse_reconciliation(
        self._changsha_workbook(include_meituan_tech_fee=False),
        "长沙动趣9.11-9.20.xlsx",
        scenic_id="changsha-dongqu",
        rate_hexiao=Decimal("0.93"), rate_settle=Decimal("0.96"),
    )
    meituan = next(item for item in parsed["platforms"] if item["platform"] == "美团")
    self.assertEqual(meituan["supplier_received"], Decimal("100.00"))

def test_changsha_required_platform_amount_columns_are_reported(self):
    cases = (("应付金额", "应付金额"), ("结算价金额", "结算价金额"))
    for omitted, expected in cases:
        with self.subTest(omitted=omitted), self.assertRaisesRegex(ValueError, expected):
            ticket_ledger.parse_reconciliation(
                self._changsha_workbook(omitted_header=omitted),
                "长沙动趣9.11-9.20.xlsx",
                scenic_id="changsha-dongqu",
            )
```

把旧快照测试输入增加非法列表形态，证明它仍回退而不报错：

```python
legacy_json = json.dumps([{
    "r": "90", "cs": "100", "cd": "-2", "ct": "-3", "co": "legacy",
}])
```

期望仍为佣金 `13.00`、出版应得 `77.00`。

- [ ] **Step 3: 运行解析器测试确认失败原因准确**

```powershell
$env:PYTHONPATH=".;D:/Investment-management/.test-deps"
python -m unittest tests.test_ticket_ledger_ctrip_parser.TicketLedgerCtripParserTest.test_changsha_douyin_uses_signed_five_column_formula_and_snapshot tests.test_ticket_ledger_ctrip_parser.TicketLedgerCtripParserTest.test_changsha_meituan_and_ctrip_reuse_target_platform_rules tests.test_ticket_ledger_ctrip_parser.TicketLedgerCtripParserTest.test_changsha_meituan_does_not_require_or_include_technical_fee tests.test_ticket_ledger_ctrip_parser.TicketLedgerCtripParserTest.test_changsha_required_platform_amount_columns_are_reported tests.test_ticket_ledger_ctrip_parser.TicketLedgerCtripParserTest.test_changsha_legacy_snapshot_defaults_platform_fee_to_zero -v
```

Expected: 当前快照没有 `co`；长沙美团仍返回 `95.00`；缺技术服务费时报错；缺主金额列未给出预期错误。

- [ ] **Step 4: 将平台缺列识别回退限定在长沙**

把 `_detect_platform`、`_find_platform_header` 增加 `scenic_id` 参数，并在标准签名识别失败后增加：

```python
if scenic_id == "changsha-dongqu":
    if (
        {COL_MT_SETTLE_TYPE, COL_MT_COUNT, COL_MT_TIME}.issubset(names)
        and {COL_MT_AMOUNT, COL_MT_TECH_FEE} & names
    ):
        return "美团"
    if (
        COL_XC_FLOW_TYPE in names
        and {COL_XC_SERVICE_DATE, COL_XC_DEPARTURE_DATE, COL_XC_PAYMENT_DATE} & names
    ):
        return "携程"
```

在 `parse_reconciliation` 中调用 `_find_platform_header(rows_iter, scenic_id)`。进入长沙美团/携程分支后分别校验：

```python
if scenic_id == "changsha-dongqu" and i_amount < 0:
    raise ValueError(f"长沙动趣美团明细缺少必要列：{COL_MT_AMOUNT}")

if scenic_id == "changsha-dongqu" and i_xc_jiesuan < 0:
    raise ValueError(f"长沙动趣携程明细缺少必要列：{COL_XC_JIESUAN}")
```

不得放宽其他景区的平台识别签名。

- [ ] **Step 5: 改为长沙美团只取应付金额**

从 `_RECEIVED_RULES` 删除：

```python
("changsha-dongqu", "美团"): "amount_plus_tech_fee",
```

保留 `("zunyi-zoo", "美团")` 及鹳雀楼现有分支。这样长沙进入默认路径，只累计消费结算行的应付金额，也不再要求技术服务费。

- [ ] **Step 6: 保存并恢复抖音逐行订单实收**

长沙抖音每处理一条有效行，在当日对象上追加：

```python
if received_rule == "changsha_douyin":
    dd.setdefault("commission_order_rows", []).append(
        shishou or Decimal("0")
    )
```

将 `_days_from_daily` 改为循环构建项目；仅当日对象存在 `commission_order_rows` 时传递该键。将 `serialize_daily` 改为循环构建 JSON 项；仅存在该键时输出：

```python
item["co"] = [str(value) for value in dd["commission_order_rows"]]
```

在 `_days_from_json` 中读取：

```python
order_rows = d.get("commission_order_rows", d.get("co"))
if isinstance(order_rows, list):
    item["commission_order_rows"] = order_rows
```

`co` 缺失或不是列表时不要把该键传给计算器，使 Task 1 自动进入旧快照回退。

- [ ] **Step 7: 运行目标测试和遵义回归**

```powershell
$env:PYTHONPATH=".;D:/Investment-management/.test-deps"
python -m unittest tests.test_ticket_ledger_ctrip_parser tests.test_scenic_ledger_calculator -v
```

Expected: 长沙快照、逐行费率重算、美团 `100.00`、携程 `50.00`、缺列错误全部通过；`test_zunyi_meituan_requires_technical_service_fee` 仍通过。

- [ ] **Step 8: 检查差异并提交解析器改动**

```powershell
git diff --check -- backend/app/services/ticket_ledger.py backend/tests/test_ticket_ledger_ctrip_parser.py
git add -- backend/app/services/ticket_ledger.py backend/tests/test_ticket_ledger_ctrip_parser.py
git commit -m "fix: update Changsha platform formulas"
```

---

### Task 3: 实际文件验收与完整回归

**Files:**
- Verify: `C:\Users\dell\Desktop\长沙动趣9.11-9.20(1).xlsx`
- Verify: `backend/app/services/ledger_calculator.py`
- Verify: `backend/app/services/ticket_ledger.py`
- Verify: `backend/tests/test_scenic_ledger_calculator.py`
- Verify: `backend/tests/test_ticket_ledger_ctrip_parser.py`

**Interfaces:**
- Consumes: Task 1 和 Task 2 的最终公共入口 `parse_reconciliation(...)`。
- Produces: 三平台实际文件验收结果和全后端测试通过证据；不创建数据库记录、不修改用户文件。

- [ ] **Step 1: 用实际文件执行只读解析验收**

从仓库根目录运行：

```powershell
$env:PYTHONPATH="backend;D:/Investment-management/.test-deps"
@'
import sys
from decimal import Decimal
from pathlib import Path
from app.services.ticket_ledger import parse_reconciliation, recompute_from_json

DOUYIN = "\u6296\u97f3"
MEITUAN = "\u7f8e\u56e2"
CTRIP = "\u643a\u7a0b"
path = Path(sys.argv[1])
parsed = parse_reconciliation(
    path.read_bytes(), path.name,
    scenic_id="changsha-dongqu",
    rate_hexiao=Decimal("0.93"),
    rate_settle=Decimal("0.96"),
    commission_rate=Decimal("0.18"),
)
rows = {item["platform"]: item for item in parsed["platforms"]}
expected = {
    DOUYIN: ("52959.86", "9079.99", "40808.28", "42124.68", "1316.40"),
    MEITUAN: ("11149.05", "0.00", "10368.62", "10703.09", "334.47"),
    CTRIP: ("1075.20", "0.00", "999.94", "1032.19", "32.25"),
}
for platform, values in expected.items():
    row = rows[platform]
    actual = tuple(str(row[key]) for key in (
        "supplier_received", "suggested_commission", "def_hexiao",
        "def_jinying", "def_service_fee",
    ))
    assert actual == values, (platform, actual, values)

douyin = recompute_from_json(
    rows[DOUYIN]["daily_json"],
    Decimal("0.93"), Decimal("0.96"), None, Decimal("0.18"),
    DOUYIN, "changsha-dongqu",
)
assert douyin["publisher_due"] == Decimal("43879.87")
print("CHANGSHA_ACTUAL_FILE_OK")
'@ | python - 'C:\Users\dell\Desktop\长沙动趣9.11-9.20(1).xlsx'
```

Expected: 输出 `CHANGSHA_ACTUAL_FILE_OK`。文件保持原样，仓库中不出现该 Excel。

- [ ] **Step 2: 运行完整后端测试**

```powershell
Set-Location backend
$env:PYTHONPATH=".;D:/Investment-management/.test-deps"
python -m unittest discover -s tests -v
```

Expected: 全部通过。若出现与主工作区未提交改动有关的失败，确认执行目录仍是隔离工作树；不要把主工作区文件复制进来。

- [ ] **Step 3: 执行最终静态检查和范围审计**

```powershell
Set-Location ..
git diff --check HEAD~2..HEAD
git status --short --branch
git log --oneline --decorate -4
git diff --stat 215798f..HEAD
```

Expected:

- 工作树干净。
- 设计、计划、Task 1、Task 2 四个提交均存在。
- 代码改动只涉及两个服务文件和两个对应测试文件；文档只涉及本设计和本计划。
- 没有 Excel、数据库文件、构建产物或主工作区未提交文件进入提交。
