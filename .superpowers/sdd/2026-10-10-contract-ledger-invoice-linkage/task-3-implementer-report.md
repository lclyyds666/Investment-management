# Task 3 实施报告：审批单强关联已审批合同

## 状态

已完成。业务审批单与付款审批单不再接受手工合同编号作为关联来源；创建和草稿编辑必须选择真实、已审批合同，并保存合同编号、景区、客户名称快照。

## 变更

- `ApprovalFormCreate` 对普通业务/付款审批条件必填 `contract_id`；更新 schema 支持草稿重新选择合同，输出 schema 暴露 `contract_id` 和 `scenic_id`，并兼容历史 `scenic_id = NULL`。
- 新增 `_approved_contract` 门禁，仅允许状态为 `approved` 的合同。
- 新增 `_apply_contract_snapshot`，由合同写入 `contract_id`、`contract_no`、`scenic_id`、`customer_name`；客户端提交的 `contract_no`、`customer_name` 会被忽略，不能覆盖快照。
- 创建审批单和编辑草稿时统一应用合同门禁与快照；已有关联的草稿未重新选择合同时保留原快照，历史未关联记录必须补选合同。
- 前端移除手工合同编号与客户选择，改为加载当前用户可见合同并仅展示已审批项；选择后预览合同编号、景区和客户。
- 前端创建/更新载荷发送 `contract_id`，明确剔除 `contract_no` 和 `customer_name`。
- 前端编辑 `contract_id = null` 的历史审批单时显示“历史未关联，请补选合同后再提交”。
- 将 `ApprovalFormWorkflowApiTest` 对齐 brief 中的 `ApprovalFormApiTest`，并补充缺失/草稿合同拒绝、不可变快照、草稿换合同刷新快照测试。
- 兼容 Task 2 的合同创建必填约束，在既有工作流测试夹具中补充有效 `scenic_id` 与 `business_scopes`。

## TDD 记录

1. 先添加后端合同门禁与快照测试；旧实现返回 200 且 `contract_id` 未保存，测试按预期失败。
2. 实现最小后端门禁与快照后，新增后端测试转绿。
3. 先添加前端合同加载、载荷和历史记录测试；旧实现 3 项均按预期失败。
4. 替换前端表单和载荷后，前端定向测试 17/17 通过。

## 测试

- `cd backend; D:/Investment-management/backend/.venv/Scripts/python.exe -m unittest tests.test_workflow_api.ApprovalFormApiTest -v`
  - 结果：通过，17 项（补充草稿编辑测试前的一次完整定向运行）。
- `cd backend; D:/Investment-management/backend/.venv/Scripts/python.exe -m pytest tests/test_workflow_api.py::ApprovalFormApiTest -q`
  - 结果：通过，18 项、6 个 subtests。
- `cd backend; D:/Investment-management/backend/.venv/Scripts/python.exe -m pytest tests/test_workflow_api.py::ApprovalFormApiTest tests/test_invoice_workflow.py::test_invoice_forms_cannot_use_generic_crud_or_submit -q`
  - 结果：通过，19 项、6 个 subtests；确认通用发票审批入口继续由端点返回 403，未被合同字段校验提前改写为 422。
- `cd frontend; npm test -- src/views/approval/index.test.js`
  - 结果：通过，17/17。
- `cd backend; D:/Investment-management/backend/.venv/Scripts/python.exe -m unittest tests.test_workflow_api tests.test_workflow_engine -v`
  - 初次结果：131/132，通过；唯一失败为既有合同创建测试缺少 Task 2 新必填的 `scenic_id`、`business_scopes`。
  - 修复测试夹具后结果：通过，132/132。
- `git diff --check`
  - 结果：通过，无空白错误；Git 仅提示工作区 LF/CRLF 转换策略。

系统 Python 首次运行定向 unittest 时缺少 `openpyxl`；后续全部后端测试均使用仓库约定的 `backend/.venv` 解释器。

## 提交

- 实现提交：`b5bc89f4ba5f209c7d6d8d1839a2d4f8d3fbbafa`（`feat: link approval forms to contracts`）
- 兼容修复提交：`6b33df042bcddb23be28c9bb9461f41b00708921`（`fix: preserve invoice approval guard`）

## 风险与注意事项

- 历史未关联审批单仍可读取和打印，但任何再次编辑保存都必须补选已审批合同，这是规格要求的有意行为。
- 快照只在创建或显式重新选择合同时生成；合同后续修改不会回写审批单，避免历史数据漂移。
- 合同列表接口当前返回用户可见合同全集，前端再过滤 `status === 'approved'`；后端写入门禁仍会再次校验状态，不能通过构造请求绕过。
- 客户快照按 `party_b`、`party_a` 的顺序取值，与任务 brief 一致；若合同双方均为空则保存空客户名。

## 修复轮次 1

根据 `task-3-review-report.md` 的 2 个 Critical 与 1 个 Important 完成以下修复：

- 后端仅在新建审批单或 `contract_id` 实际变化时重建合同快照；同一合同 ID 的备注等普通编辑保留原合同编号、景区与客户快照。
- 通用提交和经办重提在任何工作流动作前拒绝 `contract_id = NULL`，返回 422 和“请先编辑补选已审批合同”；发票专用 403 门禁仍优先执行。
- 前端对历史未关联草稿/驳回单显示禁用的“请先补选合同”按钮，并在调用路径再次提示，不会打开提交弹窗或发起请求。
- 前端创建/更新载荷不再发送 `customer_id`；后端通用写入同时忽略客户端 `customer_id`、`customer_name`，避免客户外键与合同快照矛盾。

### 修复测试

- `cd backend; D:/Investment-management/backend/.venv/Scripts/python.exe -m unittest tests.test_workflow_api tests.test_workflow_engine -v`
  - 结果：通过，133/133。
- `cd backend; D:/Investment-management/backend/.venv/Scripts/python.exe -m pytest tests/test_workflow_api.py::ApprovalFormApiTest tests/test_invoice_workflow.py::test_invoice_forms_cannot_use_generic_crud_or_submit -q`
  - 结果：通过，20 项、6 个 subtests。
- `cd frontend; npm test -- src/views/approval/index.test.js`
  - 结果：通过，18/18。
- `git diff --check`
  - 结果：通过，无空白错误。

### 修复提交

- `b9b11dc5f49e5a68b3dbf3c62a0e9db6bf84a491`（`fix: preserve approval contract snapshots`）

### 剩余顾虑

- 无阻塞顾虑。全量工作流测试仍会输出既有 SQLite 线程/资源警告，但测试结果为全通过，本轮未修改相关并发测试基础设施。
