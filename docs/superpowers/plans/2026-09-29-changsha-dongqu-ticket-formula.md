# 长沙动趣门票台账专属公式 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `changsha-dongqu` 增加抖音、美团、携程专属门票解析与整期计算规则，并把门票核销率、结算率、佣金率同步为 93%、96%、18%。

**Architecture:** Excel 适配器继续负责按平台识别列、过滤有效流水并生成逐日快照，公共纯函数计算器仅在 `scenic_id == "changsha-dongqu"` 时进入整期汇总取整路径。抖音快照新增平台撮合费用和计算模式，旧快照缺字段时按零兼容；美团复用“应付金额 + 技术服务费”策略，携程复用“订单成本/结算价金额”策略。配置种子提供新默认费率，幂等 SQL 只更新生产数据库中长沙动趣门票三项费率。

**Tech Stack:** Python 3、FastAPI 服务层、`Decimal`/`ROUND_HALF_UP`、openpyxl、unittest、MySQL 8 SQL migration、Git worktree

## Global Constraints

- 业务设计以 `docs/superpowers/specs/2026-09-29-changsha-dongqu-ticket-formula-design.md` 为唯一口径。
- 仅修改 `changsha-dongqu` 门票算法；不得改变其他景区、酒店台账、API schema 或前端字段。
- 抖音费用保持 Excel 原始符号：正常扣费为负，退款冲正为正，不取绝对值。
- 抖音服务商到账 = 订单实收 + 软件服务费 + 达人服务费 + 团长服务费 + 平台撮合服务费。
- 抖音服务商佣金 = 订单实收 × 佣金率 + 达人服务费 + 团长服务费 + 平台撮合服务费；手工佣金不为空时覆盖自动值。
- 抖音出版应得 = 服务商到账 − 服务商佣金；核销、结算、服务费均在整期汇总后四舍五入到分。
- 美团只计“消费结算”，整期基数 = 应付金额 + 技术服务费；携程只计“订单成本”，整期基数 = 结算价金额。
- 平台撮合列同时接受“平台撮合服务费”和“撮合经纪服务费”；长沙抖音五项金额列缺任一项时必须列出缺失表头。
- 旧逐日 JSON 没有平台撮合字段或计算模式时必须可重算，平台撮合费用按 0 处理。
- 长沙动趣门票费率固定迁移为核销率 `0.93`、结算率 `0.96`、佣金率 `0.18`；不得改动长沙酒店费率和其他景区。
- 实施前从提交 `c6459dc` 创建隔离 worktree；主工作区已有泉城欧乐堡、鹳雀楼等未提交改动，不得覆盖或清理。
- `C:\Users\dell\Desktop\长沙动趣9.11-9.20(1).xlsx` 只用于本地验收，不复制进仓库、不提交 Git。

---

## Execution Setup

实施者先完整读取 `using-git-worktrees` 技能，在仓库外的安全目录创建分支 `feature/changsha-dongqu-ticket-formula`，并确认基线提交为 `c6459dc`：

```powershell
git rev-parse HEAD
git status --short
git worktree add ..\Investment-management-changsha -b feature/changsha-dongqu-ticket-formula c6459dc
git -C ..\Investment-management-changsha rev-parse HEAD
```

预期：最后一条输出 `c6459dc`；所有实现、测试和任务提交均在新 worktree 中进行。主工作区的未提交文件保持原样。

### Task 1: 长沙整期纯函数计算器

**Files:**
- Modify: `backend/app/services/ledger_calculator.py:43-138`
- Test: `backend/tests/test_scenic_ledger_calculator.py:12-104`

**Interfaces:**
- Consumes: `calculate_ticket_ledger(scenic_id: str, excel_data, *, supplier_received=None, rate_hexiao: Decimal, rate_settle: Decimal, commission_override=None, commission_rate: Decimal, platform: str) -> dict | None`
- Consumes: 逐日条目字段 `r/recv/received`、`cs/commission_shishou`、`cd/commission_daren`、`ct/commission_tuanzhang`、`pf/commission_platform_fee`
- Produces: `_commission_inputs(day: Mapping) -> tuple[Decimal, Decimal, Decimal, Decimal]`
- Produces: `_calculate_changsha_ticket_period(days: list[dict], *, rate_hexiao: Decimal, rate_settle: Decimal, commission_override, commission_rate: Decimal, platform: str) -> dict`
- Produces: 既有返回键 `supplier_commission`、`publisher_due`、`hexiao_amount`、`service_fee`、`jinying_amount`，金额均为两位 `Decimal`

- [ ] **Step 1: 写入长沙抖音整期公式失败测试**

在 `ScenicLedgerCalculatorTest` 增加以下测试，用两天数据证明先整期汇总佣金、再统一取整：

```python
def test_changsha_douyin_aggregates_commission_and_rates_for_period(self):
    days = [
        {
            "r": "30000.00", "cs": "30000.10", "cd": "-60.12",
            "ct": "-600.05", "pf": "0",
        },
        {
            "r": "22959.86", "cs": "26991.20", "cd": "-58.13",
            "ct": "-459.05", "pf": "0",
        },
    ]

    result = ticket_ledger.calculate_ticket_ledger(
        "changsha-dongqu",
        days,
        rate_hexiao=Decimal("0.93"),
        rate_settle=Decimal("0.96"),
        commission_rate=Decimal("0.18"),
        platform="抖音",
    )

    self.assertEqual(result["supplier_commission"], Decimal("9081.08"))
    self.assertEqual(result["publisher_due"], Decimal("43878.78"))
    self.assertEqual(result["hexiao_amount"], Decimal("40807.27"))
    self.assertEqual(result["jinying_amount"], Decimal("42123.63"))
    self.assertEqual(result["service_fee"], Decimal("1316.36"))
```

- [ ] **Step 2: 写入手工佣金覆盖和平台撮合费用失败测试**

增加两个断言场景：`pf` 必须参与自动佣金；传入 `commission_override=Decimal("9000")` 时必须完整替代自动佣金。

```python
def test_changsha_douyin_platform_fee_and_manual_commission_override(self):
    days = [{
        "r": "86", "cs": "100", "cd": "-2", "ct": "-3", "pf": "-4",
    }]
    automatic = ticket_ledger.calculate_ticket_ledger(
        "changsha-dongqu", days,
        rate_hexiao=Decimal("0.93"), rate_settle=Decimal("0.96"),
        commission_rate=Decimal("0.18"), platform="抖音",
    )
    manual = ticket_ledger.calculate_ticket_ledger(
        "changsha-dongqu", days,
        rate_hexiao=Decimal("0.93"), rate_settle=Decimal("0.96"),
        commission_rate=Decimal("0.18"),
        commission_override=Decimal("10.25"), platform="抖音",
    )

    self.assertEqual(automatic["supplier_commission"], Decimal("9.00"))
    self.assertEqual(manual["supplier_commission"], Decimal("10.25"))
    self.assertEqual(manual["publisher_due"], Decimal("75.75"))
```

- [ ] **Step 3: 写入长沙非抖音整期取整与非长沙回归测试**

同一组极小金额在长沙携程应先汇总再取整，其他景区继续逐日取整：

```python
def test_changsha_non_douyin_rounds_period_without_changing_other_scenics(self):
    days = [{"r": "0.01"}, {"r": "0.01"}]
    changsha = ticket_ledger.calculate_ticket_ledger(
        "changsha-dongqu", days,
        rate_hexiao=Decimal("0.50"), rate_settle=Decimal("0.50"),
        platform="携程",
    )
    legacy = ticket_ledger.calculate_ticket_ledger(
        "zunyi-zoo", days,
        rate_hexiao=Decimal("0.50"), rate_settle=Decimal("0.50"),
        platform="携程",
    )

    self.assertEqual(changsha["hexiao_amount"], Decimal("0.01"))
    self.assertEqual(changsha["jinying_amount"], Decimal("0.01"))
    self.assertEqual(legacy["hexiao_amount"], Decimal("0.02"))
    self.assertEqual(legacy["jinying_amount"], Decimal("0.02"))
```

- [ ] **Step 4: 运行定向测试并确认失败原因**

Run:

```powershell
Set-Location backend
$env:PYTHONPATH='.'
python -m unittest tests.test_scenic_ledger_calculator.ScenicLedgerCalculatorTest.test_changsha_douyin_aggregates_commission_and_rates_for_period tests.test_scenic_ledger_calculator.ScenicLedgerCalculatorTest.test_changsha_douyin_platform_fee_and_manual_commission_override tests.test_scenic_ledger_calculator.ScenicLedgerCalculatorTest.test_changsha_non_douyin_rounds_period_without_changing_other_scenics -v
```

Expected: FAIL；当前 `_commission_inputs` 不读取 `pf`，且 `calculate_ticket_ledger` 仍逐日取整。

- [ ] **Step 5: 扩展佣金输入并实现长沙整期计算函数**

在 `ledger_calculator.py` 中让第四项输入兼容长名与 compact key，并把原 `_distribute_commission` 的解包同步为四元组；通用路径加入第四项但旧快照默认为 0，因此其他景区结果不变：

```python
def _commission_inputs(day: Mapping) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    return (
        _dec(_first_present(day, "commission_shishou", "cs", "shishou", "s")),
        _dec(_first_present(day, "commission_daren", "cd", "daren", "d")),
        _dec(_first_present(day, "commission_tuanzhang", "ct", "tuanzhang", "t")),
        _dec(_first_present(day, "commission_platform_fee", "pf", "platform_fee")),
    )
```

新增专属计算函数，抖音只在整期合计后做一次佣金取整，非抖音佣金为零：

```python
def _calculate_changsha_ticket_period(
    days: list[dict], *, rate_hexiao: Decimal, rate_settle: Decimal,
    commission_override, commission_rate: Decimal, platform: str,
) -> dict:
    received_total = sum(
        (_dec(day.get("received", day.get("recv", day.get("r", 0)))) for day in days),
        Decimal("0"),
    )
    if platform == "抖音":
        shishou = daren = tuanzhang = platform_fee = Decimal("0")
        for day in days:
            row_shishou, row_daren, row_tuanzhang, row_platform_fee = _commission_inputs(day)
            shishou += row_shishou
            daren += row_daren
            tuanzhang += row_tuanzhang
            platform_fee += row_platform_fee
        automatic = quantize_money(
            shishou * (commission_rate or Decimal("0"))
            + daren + tuanzhang + platform_fee
        )
        commission = (
            automatic if commission_override is None
            else quantize_money(_dec(commission_override))
        )
    else:
        commission = Decimal("0")
    publisher_due = quantize_money(received_total - commission)
    hexiao = quantize_money(publisher_due * (rate_hexiao or Decimal("0")))
    settle = quantize_money(publisher_due * (rate_settle or Decimal("0")))
    return {
        "supplier_commission": quantize_money(commission),
        "publisher_due": publisher_due,
        "hexiao_amount": hexiao,
        "service_fee": quantize_money(settle - hexiao),
        "jinying_amount": settle,
    }
```

在 `calculate_ticket_ledger` 取得 `days` 后、通用逐日分摊前，仅对长沙抖音/美团/携程调用该函数，并补上 `scenic_id`：

```python
if sid == "changsha-dongqu" and platform in {"抖音", "美团", "携程"}:
    result = _calculate_changsha_ticket_period(
        days,
        rate_hexiao=rate_hexiao,
        rate_settle=rate_settle,
        commission_override=commission_override,
        commission_rate=commission_rate,
        platform=platform,
    )
    return {"scenic_id": sid, **result}
```

同步 `_distribute_commission` 内的列表推导、到账权重计算和目标日选择，把四元组第四项加进佣金公式但不改变前三项逻辑；旧数据第四项为 0。

- [ ] **Step 6: 运行计算器测试**

Run:

```powershell
python -m unittest tests.test_scenic_ledger_calculator -v
```

Expected: PASS；长沙预期金额准确，鹳雀楼、泉城及通用逐日路径回归通过。

- [ ] **Step 7: 提交纯函数计算器**

```powershell
git add -- backend/app/services/ledger_calculator.py backend/tests/test_scenic_ledger_calculator.py
git diff --cached --check
git commit -m "feat: add Changsha ticket period calculation"
```

### Task 2: 长沙 Excel 解析与逐日快照兼容

**Files:**
- Modify: `backend/app/services/ticket_ledger.py:42-95`
- Modify: `backend/app/services/ticket_ledger.py:287-640`
- Modify: `backend/app/services/ticket_ledger.py:652-718`
- Test: `backend/tests/test_ticket_ledger_ctrip_parser.py:19-405`

**Interfaces:**
- Consumes: `parse_reconciliation(content: bytes, filename: str, *, scenic_id: str, rate_hexiao: Decimal, rate_settle: Decimal, commission_rate: Decimal, commission_override=None, ticket_product: str) -> dict`
- Consumes: Task 1 的 `calculate_ticket_ledger` 长沙整期分支及 `commission_platform_fee/pf` 输入
- Produces: `_RECEIVED_RULES[("changsha-dongqu", "抖音")] == "changsha_douyin"`
- Produces: `_RECEIVED_RULES[("changsha-dongqu", "美团")] == "amount_plus_tech_fee"`，遵义美团也使用该通用策略名
- Produces: 长沙抖音 `daily_json` 每日对象包含 `pf` 和 `m: "changsha_douyin"`
- Produces: `_days_from_json` 对 `pf` 缺失返回 `commission_platform_fee = Decimal("0")`，并保留已有 `calculation_mode/m` 字段

- [ ] **Step 1: 新增可复用的长沙三平台合成工作簿测试夹具**

在测试类中增加 `_changsha_workbook`，覆盖负费用、正数冲正、平台撮合表头别名、美团非消费流水和携程非订单成本流水：

```python
@staticmethod
def _changsha_workbook(platform_fee_header="平台撮合服务费", omitted_header=None) -> bytes:
    wb = Workbook()
    douyin = wb.active
    douyin.title = "抖音"
    headers = [
        "订单实收", "软件服务费", "达人服务费", "团长服务费",
        platform_fee_header, "核销时间",
    ]
    headers = [header for header in headers if header != omitted_header]
    douyin.append(headers)
    rows = [
        [100, -5, -2, -3, -4, datetime(2026, 9, 11, 10, 0)],
        [-20, 1, 1, 1, 1, datetime(2026, 9, 12, 10, 0)],
    ]
    full_headers = [
        "订单实收", "软件服务费", "达人服务费", "团长服务费",
        platform_fee_header, "核销时间",
    ]
    for values in rows:
        by_header = dict(zip(full_headers, values))
        douyin.append([by_header[header] for header in headers])

    meituan = wb.create_sheet("美团")
    meituan.append(["结算方式", "应付金额", "技术服务费", "张数", "时间"])
    meituan.append(["消费结算", 100, -5, 1, datetime(2026, 9, 11)])
    meituan.append(["退款结算", 999, 0, 1, datetime(2026, 9, 12)])

    ctrip = wb.create_sheet("携程")
    ctrip.append(["结算价金额", "流水类型", "使用份数", "出发时间"])
    ctrip.append([50, "订单成本", 1, datetime(2026, 9, 11)])
    ctrip.append([999, "调账", 1, datetime(2026, 9, 12)])

    output = BytesIO()
    wb.save(output)
    wb.close()
    return output.getvalue()
```

- [ ] **Step 2: 写入抖音公式、别名和快照失败测试**

解析核销率 93%、结算率 96%、佣金率 18%，验证两行整期汇总结果与 compact JSON：

```python
def test_changsha_douyin_uses_signed_five_column_formula_and_snapshot(self):
    parsed = ticket_ledger.parse_reconciliation(
        self._changsha_workbook(), "长沙动趣9.11-9.20.xlsx",
        scenic_id="changsha-dongqu",
        rate_hexiao=Decimal("0.93"), rate_settle=Decimal("0.96"),
        commission_rate=Decimal("0.18"),
    )
    by_platform = {item["platform"]: item for item in parsed["platforms"]}
    douyin = by_platform["抖音"]

    self.assertEqual(douyin["supplier_received"], Decimal("70.00"))
    self.assertEqual(douyin["suggested_commission"], Decimal("8.40"))
    self.assertEqual(douyin["def_hexiao"], Decimal("57.29"))
    self.assertEqual(douyin["def_jinying"], Decimal("59.14"))
    self.assertEqual(douyin["def_service_fee"], Decimal("1.85"))
    snapshot = json.loads(douyin["daily_json"])
    self.assertEqual(snapshot[0]["pf"], "-4")
    self.assertEqual(snapshot[0]["m"], "changsha_douyin")

    alias_parsed = ticket_ledger.parse_reconciliation(
        self._changsha_workbook("撮合经纪服务费"), "长沙动趣9.11-9.20.xlsx",
        scenic_id="changsha-dongqu", commission_rate=Decimal("0.18"),
    )
    self.assertEqual(alias_parsed["supplier_received"], Decimal("70.00"))
```

- [ ] **Step 3: 写入美团、携程复用策略失败测试**

```python
def test_changsha_meituan_and_ctrip_reuse_target_platform_rules(self):
    parsed = ticket_ledger.parse_reconciliation(
        self._changsha_workbook(), "长沙动趣9.11-9.20.xlsx",
        scenic_id="changsha-dongqu",
        rate_hexiao=Decimal("0.93"), rate_settle=Decimal("0.96"),
        commission_rate=Decimal("0.18"),
    )
    by_platform = {item["platform"]: item for item in parsed["platforms"]}

    self.assertEqual(by_platform["美团"]["supplier_received"], Decimal("95.00"))
    self.assertEqual(by_platform["美团"]["def_hexiao"], Decimal("88.35"))
    self.assertEqual(by_platform["美团"]["def_jinying"], Decimal("91.20"))
    self.assertEqual(by_platform["携程"]["supplier_received"], Decimal("50.00"))
    self.assertEqual(by_platform["携程"]["def_hexiao"], Decimal("46.50"))
    self.assertEqual(by_platform["携程"]["def_jinying"], Decimal("48.00"))
```

- [ ] **Step 4: 写入缺列错误和旧 JSON 兼容失败测试**

对五个金额列逐一删除并检查错误信息包含具体列名；另用不含 `pf`/`m` 的历史快照重算，平台撮合费必须按零：

```python
def test_changsha_douyin_requires_all_five_amount_columns(self):
    for header in (
        "订单实收", "软件服务费", "达人服务费", "团长服务费", "平台撮合服务费",
    ):
        with self.subTest(header=header), self.assertRaisesRegex(ValueError, header):
            ticket_ledger.parse_reconciliation(
                self._changsha_workbook(omitted_header=header),
                "长沙动趣9.11-9.20.xlsx",
                scenic_id="changsha-dongqu",
            )

def test_changsha_legacy_snapshot_defaults_platform_fee_to_zero(self):
    legacy_json = json.dumps([{
        "r": "90", "cs": "100", "cd": "-2", "ct": "-3",
    }])
    result = ticket_ledger.recompute_from_json(
        legacy_json,
        Decimal("0.93"), Decimal("0.96"), None, Decimal("0.18"),
        "抖音", "changsha-dongqu",
    )
    self.assertEqual(result["supplier_commission"], Decimal("13.00"))
    self.assertEqual(result["publisher_due"], Decimal("77.00"))
```

如果现有工作区基线已经包含其他算法的 `calculation_mode/m`，本测试追加 `changsha_douyin` 值，不能删除或重命名已有模式。

- [ ] **Step 5: 运行解析器测试并确认失败原因**

Run:

```powershell
python -m unittest tests.test_ticket_ledger_ctrip_parser.TicketLedgerCtripParserTest.test_changsha_douyin_uses_signed_five_column_formula_and_snapshot tests.test_ticket_ledger_ctrip_parser.TicketLedgerCtripParserTest.test_changsha_meituan_and_ctrip_reuse_target_platform_rules tests.test_ticket_ledger_ctrip_parser.TicketLedgerCtripParserTest.test_changsha_douyin_requires_all_five_amount_columns tests.test_ticket_ledger_ctrip_parser.TicketLedgerCtripParserTest.test_changsha_legacy_snapshot_defaults_platform_fee_to_zero -v
```

Expected: FAIL；长沙尚未独立读取团长与平台撮合列，也未要求五列或写入 `pf/m`。

- [ ] **Step 6: 增加长沙策略常量和严格列校验**

新增平台撮合标准列和别名，长沙抖音使用五个独立索引，不能继续复用通用规则中“团长/撮合二选一”的第三个费用索引：

```python
COL_PLATFORM_MATCH = "平台撮合服务费"
COL_PLATFORM_MATCH_ALIASES = (COL_PLATFORM_MATCH, COL_CUOHE)

_RECEIVED_RULES = {
    ("zunyi-zoo", "抖音"): "zunyi_douyin",
    ("zunyi-zoo", "美团"): "amount_plus_tech_fee",
    ("nanyang-wildlife", "抖音"): "nanyang_douyin",
    ("changsha-dongqu", "抖音"): "changsha_douyin",
    ("changsha-dongqu", "美团"): "amount_plus_tech_fee",
}
```

为使“订单实收”本身缺失时仍能进入长沙的字段级校验，扩展 `_detect_platform` 的抖音特征：有“核销时间”且包含订单实收列，或至少包含三种抖音费用列，即识别为抖音。其他平台签名保持不变：

```python
douyin_fee_names = {
    COL_RUANJIAN, COL_DAREN, COL_TUANZHANG, COL_PLATFORM_MATCH, COL_CUOHE,
}
if (
    COL_HEXIAO_TIME in names
    and (
        bool({COL_SHISHOU, COL_SHISHOU_CURRENT} & names)
        or len(douyin_fee_names & names) >= 3
    )
):
    return "抖音"
```

当 `received_rule == "changsha_douyin"` 时分别定位 `i_ruanjian`、`i_daren`、`i_tuanzhang`、`i_platform_fee`，构造如下缺列列表：

```python
required = (
    ((COL_SHISHOU_CURRENT, COL_SHISHOU), i_shishou),
    ((COL_RUANJIAN,), i_ruanjian),
    ((COL_DAREN,), i_daren),
    ((COL_TUANZHANG,), i_tuanzhang),
    (COL_PLATFORM_MATCH_ALIASES, i_platform_fee),
)
missing = [names[0] for names, index in required if index < 0]
if missing:
    raise ValueError(f"长沙动趣抖音明细缺少必要列：{'、'.join(missing)}")
```

订单实收缺失时错误名称使用文件实际支持的首选名“订单实收”；平台撮合两个别名都缺少时错误名称使用“平台撮合服务费”。

- [ ] **Step 7: 解析长沙抖音原始符号并保存新快照字段**

长沙抖音逐行计算：

```python
base = (
    (shishou or Decimal("0"))
    + (software_fee or Decimal("0"))
    + (daren_fee or Decimal("0"))
    + (leader_fee or Decimal("0"))
    + (platform_fee or Decimal("0"))
)
commission_daren = daren_fee or Decimal("0")
commission_tuanzhang = leader_fee or Decimal("0")
commission_platform_fee = platform_fee or Decimal("0")
```

`daily` 默认对象增加 `platform_fee`、`commission_platform_fee`、`calculation_mode`；长沙写入 `changsha_douyin`，其他平台/景区写空值并保持既有金额：

```python
dd["platform_fee"] += platform_fee or Decimal("0")
dd["commission_platform_fee"] += commission_platform_fee
dd["calculation_mode"] = "changsha_douyin"
```

把美团 `zunyi_meituan` 判断改为 `amount_plus_tech_fee`，缺列提示改成由 `scenic_id` 获取景区名称或使用“美团明细缺少必要列：技术服务费”，让遵义和长沙共用同一解析策略而不写死遵义名称。鹳雀楼现有专属规则继续保留。

- [ ] **Step 8: 扩展序列化、反序列化并兼容旧快照**

`_days_from_daily` 和 `serialize_daily` 使用 `.get(..., Decimal("0"))`，避免其他平台旧 daily 对象没有新字段时报错：

```python
"commission_platform_fee": dd.get("commission_platform_fee", Decimal("0")),
"calculation_mode": dd.get("calculation_mode", ""),
```

compact JSON 写入：

```python
"pf": str(dd.get("commission_platform_fee", Decimal("0"))),
"m": dd.get("calculation_mode", ""),
```

`_days_from_json` 读取长短字段，并用零兼容历史 JSON：

```python
"commission_platform_fee": (
    _num(d.get("commission_platform_fee", d.get("pf"))) or Decimal("0")
),
"calculation_mode": d.get("calculation_mode", d.get("m", "")),
```

若执行分支基线已使用 `m` 保存其他 `calculation_mode`，沿用同一字段；`pf` 专用于平台撮合费，不能复用 `m`。

- [ ] **Step 9: 运行解析器全文件与计算器回归**

Run:

```powershell
python -m unittest tests.test_ticket_ledger_ctrip_parser tests.test_scenic_ledger_calculator -v
```

Expected: PASS；长沙三平台新测试、遵义美团、鹳雀楼、福州免佣及历史 JSON 测试全部通过。

- [ ] **Step 10: 提交 Excel 解析与快照变更**

```powershell
git add -- backend/app/services/ticket_ledger.py backend/tests/test_ticket_ledger_ctrip_parser.py
git diff --cached --check
git commit -m "feat: parse Changsha ticket statements"
```

### Task 3: 长沙门票配置种子与生产迁移

**Files:**
- Modify: `backend/app/services/scenic_config.py:20-42`
- Create: `backend/migrations/20260929_changsha_dongqu_ticket_formula.sql`
- Test: `backend/tests/test_scenic_config.py:75-83`
- Test: `backend/tests/test_scenic_config.py:100-142`

**Interfaces:**
- Consumes: `get_effective_config(db: Session | None, scenic_id: str) -> EffectiveScenicConfig`
- Produces: `SCENIC_SEEDS` 中长沙门票 `ticket_rate_hexiao=Decimal("0.93")`、`ticket_rate_settle=Decimal("0.96")`、`ticket_commission_rate=Decimal("0.18")`
- Produces: SQL 只更新 `biz_scenic_config.rate_hexiao`、`rate_settle`、`commission_rate`，定位 `scenic_id='changsha-dongqu'`

- [ ] **Step 1: 更新种子期望并新增迁移文本契约失败测试**

把 `test_changsha_dongqu_uses_ticket_defaults` 三项期望改为新费率，并增加：

```python
def test_changsha_ticket_formula_migration_only_updates_target_ticket_rates(self):
    migration = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "20260929_changsha_dongqu_ticket_formula.sql"
    ).read_text(encoding="utf-8")

    self.assertIn("`rate_hexiao` = 0.93", migration)
    self.assertIn("`rate_settle` = 0.96", migration)
    self.assertIn("`commission_rate` = 0.18", migration)
    self.assertIn("WHERE `scenic_id` = 'changsha-dongqu'", migration)
    self.assertNotIn("hotel_rate_hexiao", migration)
    self.assertNotIn("hotel_rate_settle", migration)
    self.assertNotIn("hotel_commission_rate", migration)
```

在 `test_changsha_dongqu_uses_ticket_defaults` 同时锁定长沙酒店 fallback 仍为原值，防止门票 seed 的三项新费率泄漏到酒店配置：

```python
self.assertEqual(changsha.hotel_rate_hexiao, Decimal("0.90"))
self.assertEqual(changsha.hotel_rate_settle, Decimal("0.94"))
self.assertEqual(changsha.hotel_commission_rate, Decimal("0.06"))
```

- [ ] **Step 2: 运行配置测试并确认失败原因**

Run:

```powershell
python -m unittest tests.test_scenic_config.ScenicConfigTest.test_changsha_dongqu_uses_ticket_defaults tests.test_scenic_config.ScenicConfigTest.test_changsha_ticket_formula_migration_only_updates_target_ticket_rates -v
```

Expected: FAIL；种子仍为 90%/94%/6%，迁移文件尚不存在。

- [ ] **Step 3: 更新长沙门票种子且保持酒店快照语义**

修改长沙 tuple 的门票三项费率：

```python
("changsha-dongqu", "长沙动趣王国", 70, SYSTEM_TICKET_PRODUCT, "0.93", "0.96", "0.18", None),
```

不要改系统默认常量或其他 seed。由于 `_seed_config` 当前会把 seed 的门票费率同时复制到酒店 fallback，增加长沙专属隔离，确保本次只改变门票：

```python
hotel_hexiao = Decimal(hexiao)
hotel_settle = Decimal(settle)
hotel_commission = Decimal(commission_rate)
if sid == "changsha-dongqu":
    hotel_hexiao = SYSTEM_HOTEL_RATE_HEXIAO
    hotel_settle = SYSTEM_HOTEL_RATE_SETTLE
    hotel_commission = SYSTEM_HOTEL_COMMISSION_RATE
```

构造 `EffectiveScenicConfig` 时把 `hotel_rate_hexiao`、`hotel_rate_settle`、`hotel_commission_rate` 分别改用这三个局部值。这样全新、未落库的长沙门票 fallback 是 93%/96%/18%，酒店仍是 90%/94%/6%；生产迁移同样不更新已有数据库酒店列。

- [ ] **Step 4: 新建幂等、定向 SQL 迁移**

创建：

```sql
-- Update only Changsha Dongqu ticket rates. Re-running is idempotent.
UPDATE `biz_scenic_config`
SET
  `rate_hexiao` = 0.93,
  `rate_settle` = 0.96,
  `commission_rate` = 0.18
WHERE `scenic_id` = 'changsha-dongqu';
```

该语句重复执行结果相同，不写 `hotel_*`、景区名称、排序、产品或默认佣金。

- [ ] **Step 5: 运行配置全文件测试**

Run:

```powershell
python -m unittest tests.test_scenic_config -v
```

Expected: PASS；长沙门票默认费率与迁移契约通过，其他景区配置回归不变。

- [ ] **Step 6: 提交配置与迁移**

```powershell
git add -- backend/app/services/scenic_config.py backend/migrations/20260929_changsha_dongqu_ticket_formula.sql backend/tests/test_scenic_config.py
git diff --cached --check
git commit -m "fix: update Changsha ticket rates"
```

### Task 4: 真实文件验收、全量回归与集成准备

**Files:**
- Verify: `backend/app/services/ledger_calculator.py`
- Verify: `backend/app/services/ticket_ledger.py`
- Verify: `backend/app/services/scenic_config.py`
- Verify: `backend/migrations/20260929_changsha_dongqu_ticket_formula.sql`
- Verify: `C:\Users\dell\Desktop\长沙动趣9.11-9.20(1).xlsx`

**Interfaces:**
- Consumes: `parse_reconciliation(...)` 对真实三工作表文件的返回值
- Produces: 抖音 `52959.86 / 9081.08 / 43878.78 / 40807.27 / 42123.63 / 1316.36`
- Produces: 美团 `11988.70 / 0.00 / 11988.70 / 11149.49 / 11509.15 / 359.66`
- Produces: 携程 `1075.20 / 0.00 / 1075.20 / 999.94 / 1032.19 / 32.25`

- [ ] **Step 1: 新增一次性真实文件验收命令并执行**

不把脚本或 Excel 写入仓库，直接从 `backend` 运行：

```powershell
$env:PYTHONPATH='.'
@'
from decimal import Decimal
from pathlib import Path
from app.services.ticket_ledger import parse_reconciliation

source = Path(r"C:\Users\dell\Desktop\长沙动趣9.11-9.20(1).xlsx")
parsed = parse_reconciliation(
    source.read_bytes(), source.name,
    scenic_id="changsha-dongqu",
    rate_hexiao=Decimal("0.93"),
    rate_settle=Decimal("0.96"),
    commission_rate=Decimal("0.18"),
)
for item in parsed["platforms"]:
    print(
        item["platform"], item["supplier_received"], item["suggested_commission"],
        item["supplier_received"] - item["suggested_commission"],
        item["def_hexiao"], item["def_jinying"], item["def_service_fee"],
    )
'@ | python -
```

Expected:

```text
抖音 52959.86 9081.08 43878.78 40807.27 42123.63 1316.36
美团 11988.70 0.00 11988.70 11149.49 11509.15 359.66
携程 1075.20 0.00 1075.20 999.94 1032.19 32.25
```

若 Desktop 文件读取触发权限限制，申请只读访问该已由用户指定的单一文件；不得复制文件到 Git 工作树。

- [ ] **Step 2: 运行三个相关测试文件**

```powershell
python -m unittest tests.test_scenic_ledger_calculator tests.test_ticket_ledger_ctrip_parser tests.test_scenic_config -v
```

Expected: PASS。

- [ ] **Step 3: 运行后端全量测试**

```powershell
python -m unittest discover -s tests -v
```

Expected: PASS。若出现与本分支无关且在 `c6459dc` 基线同样存在的失败，记录测试名、错误和基线复现结果，不修改无关模块。

- [ ] **Step 4: 检查差异、提交边界与工作树状态**

```powershell
git diff --check c6459dc..HEAD
git status --short
git log --oneline c6459dc..HEAD
git diff --stat c6459dc..HEAD
```

Expected: 差异只包含本计划列出的 7 个实现/测试/迁移文件；工作树为空；共有三个任务提交。

- [ ] **Step 5: 对照业务验收清单进行最终复核**

逐项确认：

```text
[x] 抖音五项带符号费用同时进入服务商到账
[x] 软件服务费不进入佣金
[x] 达人、团长、平台撮合费进入佣金
[x] 手工佣金覆盖自动佣金
[x] 三个平台均整期汇总后取整
[x] 美团仅消费结算且加技术服务费
[x] 携程仅订单成本且使用结算价金额
[x] 旧 JSON 缺 pf/m 可重算
[x] 长沙门票为 93%/96%/18%
[x] 其他景区及酒店结果不变
```

- [ ] **Step 6: 按完成分支流程准备集成**

完整读取 `finishing-a-development-branch` 技能，先执行其验证步骤，再把 `feature/changsha-dongqu-ticket-formula` 与主工作区未提交算法改动逐文件比较。由于 `ledger_calculator.py`、`ticket_ledger.py` 及对应测试在主工作区存在重叠改动，未经比较不得直接覆盖；优先用非破坏性 cherry-pick/三方合并并保留主工作区现有泉城欧乐堡、鹳雀楼逻辑。

本任务到此只完成实现分支和验收；推送、生产数据库迁移与服务器部署需在用户明确选择集成方式后执行。
