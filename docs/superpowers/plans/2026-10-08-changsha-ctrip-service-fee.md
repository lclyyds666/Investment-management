# 长沙携程服务商到账修正 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans (recommended). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让长沙动趣携程服务商到账按订单成本与平台服务费的签名净额计算。

**Architecture:** 在现有 `ticket_ledger.py` 携程解析分支内，仅对长沙放宽计入流水类型为订单成本和平台服务费，并继续使用结算价金额作为金额来源。通过解析器回归测试和真实 Excel 只读验收锁定结果，其他景区路径不变。

**Tech Stack:** Python 3.13、Decimal、openpyxl、标准库 unittest。

## Global Constraints

- 仅修改 `scenic_id = "changsha-dongqu"` 的携程门票算法。
- 长沙携程服务商到账为订单成本与平台服务费的签名结算价金额合计。
- 不得对流水金额取绝对值。
- 不修改美团、抖音、同程、酒店台账、数据库结构、API schema 或景区配置。
- 不复制、修改或提交用户原始 Excel 文件。

---

### Task 1: 修正携程流水计入规则并增加回归测试

**Files:**
- Modify: `backend/app/services/ticket_ledger.py` 携程流水类型筛选
- Test: `backend/tests/test_ticket_ledger_ctrip_parser.py` 长沙携程解析测试

**Interfaces:**
- Consumes: 携程工作表中的 `结算价金额`、`流水类型`、携程订单号及现有景区筛选。
- Produces: `parse_reconciliation(...)` 返回的长沙携程 `supplier_received`。

- [ ] **Step 1: 写入失败测试**

构造长沙携程工作表，加入同一订单的 `订单成本=100`、`平台服务费=-8`，加入一条应忽略的其他流水 `=5`，断言服务商到账为 `92.00`，并保留现有旧测试的其他景区行为。

- [ ] **Step 2: 运行目标测试确认失败**

```powershell
$env:PYTHONPATH=".;D:/Investment-management/.test-deps"
python -m unittest tests.test_ticket_ledger_ctrip_parser.TicketLedgerCtripParserTest.test_changsha_ctrip_includes_signed_platform_service_fee -v
```

预期当前实现返回 `100.00`，测试失败。

- [ ] **Step 3: 实现最小修改**

在携程分支保留现有景区过滤和 `结算价金额` 读取；长沙只跳过非 `订单成本`、非 `平台服务费` 流水，其他景区继续只计入 `订单成本`：

```python
if flow_type:
    allowed_flows = {XC_ORDER_COST}
    if scenic_id == "changsha-dongqu":
        allowed_flows.add("平台服务费")
    if flow_type not in allowed_flows:
        continue
```

- [ ] **Step 4: 运行专项回归测试**

```powershell
$env:PYTHONPATH=".;D:/Investment-management/.test-deps"
python -m unittest tests.test_ticket_ledger_ctrip_parser tests.test_scenic_ledger_calculator -v
```

预期所有携程、长沙公式、遵义及其他景区测试通过。

- [ ] **Step 5: 用真实文件只读验收**

调用 `parse_reconciliation` 读取 `C:\Users\dell\Desktop\长沙动趣9.11-9.20(1).xlsx`，断言携程 `supplier_received == Decimal("989.12")`，并核对抖音、美团数值未变化。

- [ ] **Step 6: 检查差异并提交**

```powershell
git diff --check
git add backend/app/services/ticket_ledger.py backend/tests/test_ticket_ledger_ctrip_parser.py docs/superpowers/specs/2026-10-08-changsha-ctrip-service-fee-design.md docs/superpowers/plans/2026-10-08-changsha-ctrip-service-fee.md
git commit -m "fix: include Changsha Ctrip service fees"
```
