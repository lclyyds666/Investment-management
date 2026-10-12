# Task 4 Report: 战略总览集成回归

## 验收结论

门票/酒店台账快照 → `build_scenic_completion()` → 共用财务 dashboard → `/operation/financial` → DataScreen 省份指标坞的单向数据链路通过专项测试和生产构建验证。未发现阻断问题，现有经营指标、权限和全国/省份交互保持兼容。

## 后端专项回归

命令：

```powershell
cd D:/Investment-management/.worktrees/operation-forecast-supply-chain-closure/backend
$env:PYTHONPATH='D:/Investment-management/.test-deps'
python -m unittest tests.test_scenic_completion tests.test_financial_ledger_metrics tests.test_scenic_analytics tests.test_operation_api -v
```

结果：`Ran 16 tests`，`OK`。

验证内容：

- 同期多平台累计核销全部求和，最新期次待核销余额只取一次。
- 门票与酒店独立输出，同景区形成两条完成度明细。
- 明确业务日期优先于较晚导入但缺失日期的历史期次；全缺日期时按 `created_at, id` 稳定选择。
- 零分母返回 `completion_rate = null`。
- 共用 dashboard 仍只查询一次门票台账、一次酒店台账，并保留原财务指标。
- `/operation/financial` 继续使用 `supply.dashboard.view` 权限并正确序列化完成度。

## 前端专项回归

Task 4 简报列出的 `src/components/screen/ScreenMap.test.js` 与 `src/api/operation.test.js` 在当前仓库不存在。其地图金额格式、湖南业务节点与财务 API 消费已在现有 `DataScreen.test.js` 中覆盖；同时补跑屏幕入口测试。

命令：

```powershell
cd D:/Investment-management/.worktrees/operation-forecast-supply-chain-closure/frontend
npm test -- src/components/screen/DataScreen.test.js src/views/screen/index.test.js
```

结果：`2 passed` test files，`9 passed` tests。

验证内容：

- 同省多个景区分别展示，每个 `scenic_id + business_type` 仅一行。
- 同景区门票在酒店之前，跨景区按中文名称稳定排序。
- 贵州零分母显示 `—`，返回全国后明细消失。
- 切换省份不残留上一省数据，轮询刷新后重新进入使用最新响应。
- 原全国/区域金额换算、AI 助手入口、湖南地图节点和全屏退出行为保持不变。

## 生产构建

命令：

```powershell
cd D:/Investment-management/.worktrees/operation-forecast-supply-chain-closure/frontend
npm run build
```

结果：成功转换 `2507 modules`，`✓ built in 9.69s`，生成 `frontend/dist`。存在既有的 VueUse PURE 注释和大 chunk 警告，无构建错误。

## 数值与稳定性验收

使用真实 `TicketLedger` / `HotelLedger` ORM 行运行无数据库聚合场景：

- 门票同期两平台：累计核销 `1.00`，共享待核销 `2.00` 只取一次，完成率 `33.33%`。
- 同景区酒店：累计核销 `6.00`，待核销 `4.00`，完成率 `60.00%`。
- 输出顺序稳定为酒店、门票；前端展示顺序再按景区名称及门票、酒店规则稳定处理。
- Vue 列表键为 `${scenic_id}-${business_type}`，轮询刷新前后键不变，不产生重复行。

首次手工脚本未导入模型注册模块，触发 SQLAlchemy `User` 关系解析错误；补充 `import app.db.init_db` 后同一验收场景通过。该问题仅属于脚本初始化方式，不涉及生产链路或测试失败。

## 自检与范围

- `git diff --check` 通过。
- Task 4 未修改生产代码或测试代码，仅新增本集成回归报告。
- 未触碰或暂存 operation forecast、fund alert 的现有工作树改动。
- 未使用简报中的宽泛 `git add -- backend frontend`，避免纳入其他任务文件。
