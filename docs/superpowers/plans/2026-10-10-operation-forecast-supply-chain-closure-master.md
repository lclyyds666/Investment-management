# 经营分析预测与供应链闭环总实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 分阶段交付经营分析预测、资金到期提醒、合同期限、战略完成度以及合同到资金的完整供应链闭环。

**Architecture:** 先以合同外键和“景区 + 业务类型 + 台账期次”关联记录建立统一业务主线，再增加待资金执行任务与发票资金核销。经营分析预测直接消费已确认台账快照，资金提醒和战略完成度分别复用现有权限与财务聚合接口，五个子计划均可单独测试、提交和回滚。

**Tech Stack:** FastAPI、SQLAlchemy 2、Pydantic 2、MySQL/SQLite、openpyxl、Vue 3、Pinia、Element Plus、ECharts、Vitest、Python unittest。

## Global Constraints

- 不接入第三方天气 API 或网络资讯 API。
- 预测只使用已确认门票、酒店台账，结果只即时展示和导出，不持久化。
- 自定义预测周期最长 90 天，输出结算金额、景区核销金额和订单量。
- 一份合同只属于一个景区，可覆盖多个业务类型、多个期次和全部平台。
- 审批通过只生成待资金执行任务，财务确认实际收付款后才生成资金流水。
- 发票与资金支持多对多核销，允许预付款后补进项发票。
- 历史合同更换不得改写历史台账、发票、审批和资金快照。
- 保留工作区现有用户改动；每个子计划只暂存自身文件。

---

## 子计划与执行顺序

1. `2026-10-10-contract-ledger-invoice-linkage.md`
   - 合同期限、景区和业务范围。
   - 审批单合同外键。
   - 台账期次合同关联与确认门禁。
   - 发票继承合同并保护下游已使用数据。
2. `2026-10-10-cash-execution-invoice-reconciliation.md`
   - 待资金执行任务。
   - 实际资金流水。
   - 发票资金多对多核销。
   - 预付款待补票、合同金额预警、集中待处理事项。
3. `2026-10-10-operation-analysis-forecast.md`
   - “经营数据”二级菜单。
   - 经营情况分析。
   - 影响因素表单与 Excel。
   - 可解释预测、低置信度降级和导出。
4. `2026-10-10-fund-due-login-alerts.md`
   - 所有资金查看用户每日首次登录提醒。
   - 第 30 天、逾期、结清和每日去重。
5. `2026-10-10-strategic-scenic-completion.md`
   - 省份核心经营指标中的景区完成度明细。
   - 多景区、门票/酒店拆分及最新待核销余额去重。

## 集成顺序

- [ ] **Step 1: 完成并回归合同、台账、发票关联子计划**

Run: `cd backend; python -m unittest tests.test_invoice_generation tests.test_ticket_ledger_invoice_sync tests.test_hotel_ledger_invoice_sync tests.test_workflow_api -v`

Expected: PASS；台账确认没有合同会返回 422，合法合同会随发票写入 `contract_id`。

- [ ] **Step 2: 完成并回归资金执行与核销子计划**

Run: `cd backend; python -m unittest tests.test_cash_execution tests.test_invoice_fund_reconciliation tests.test_work_items tests.test_fund_api -v`

Expected: PASS；审批不直接记账，执行后才生成资金流水，多对多分配不超额。

- [ ] **Step 3: 完成并回归分析预测子计划**

Run: `cd backend; python -m unittest tests.test_operation_analysis tests.test_operation_forecast tests.test_operation_forecast_api -v`

Expected: PASS；只读取已确认台账，90 天边界和低置信度降级正确。

- [ ] **Step 4: 完成并回归资金提醒子计划**

Run: `cd backend; python -m unittest tests.test_fund_alert_models tests.test_fund_alert_api tests.test_fund_api -v`

Expected: PASS；同一用户同一事项同一天只确认一次，次日重新出现。

- [ ] **Step 5: 完成并回归战略完成度子计划**

Run: `cd backend; python -m unittest tests.test_financial_ledger_metrics -v`

Expected: PASS；完成度按景区和业务类型拆分，零分母返回空值。

- [ ] **Step 6: 运行后端完整测试**

Run: `cd backend; python -m unittest discover -s tests -p "test_*.py" -v`

Expected: PASS；如出现与本计划无关的既有失败，记录测试名与原始错误，不修改无关模块。

- [ ] **Step 7: 运行前端完整测试与构建**

Run: `cd frontend; npm test`

Expected: PASS。

Run: `cd frontend; npm run build`

Expected: PASS，并生成 `frontend/dist`。

- [ ] **Step 8: 执行迁移幂等性验证**

Run in repository order:

```bash
mysql --default-character-set=utf8mb4 -u USER -p DATABASE < backend/migrations/20261010_contract_ledger_invoice_linkage.sql
mysql --default-character-set=utf8mb4 -u USER -p DATABASE < backend/migrations/20261010_cash_execution_reconciliation.sql
mysql --default-character-set=utf8mb4 -u USER -p DATABASE < backend/migrations/20261010_fund_alert_receipts.sql
```

Expected: 第一次执行完成合同关联、资金执行核销和提醒回执结构升级；按相同顺序第二次执行不报重复表、重复列、重复索引或重复外键错误。

- [ ] **Step 9: 完成端到端人工验收**

依次验证：新建景区合同 → 合同审批 → 门票或酒店台账关联合同并确认 → 自动生成进销项发票 → 付款审批生成待执行任务 → 财务执行实际付款 → 后补进项发票并核销 → 销项发票审批和上传 → 回款执行并核销 → 数据中心下钻 → 待处理事项归零。

- [ ] **Step 10: 提交集成回归记录**

```bash
git add -- docs/superpowers/plans backend frontend
git commit -m "test: verify operation forecast and supply chain closure"
```

提交前运行 `git diff --check`，并确认未暂存用户原有无关改动。
