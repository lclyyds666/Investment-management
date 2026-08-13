# 统一组织迁移 MySQL 排序规则兼容修复设计

## 背景

生产副本预检在执行 `20260814_position_workflow_engine.sql` 时失败：
`wf_task.required_position_code` 使用 `utf8mb4_unicode_ci`，而
`sys_position.code` 由 `20260813_unified_organization_permissions.sql`
在 MySQL 8.0.46 上按服务器默认值创建为 `utf8mb4_0900_ai_ci`。两列连接比较触发
`ERROR 1267 Illegal mix of collations`。

预检在临时数据库内执行，生产数据库、现网文件、服务和版本标记均未变更。

## 方案

在 `20260813_unified_organization_permissions.sql` 中，为所有新建组织权限域表的
`DEFAULT CHARSET=utf8mb4` 明确补充 `COLLATE=utf8mb4_unicode_ci`。

不采用以下方案：

- 不只给当前 `JOIN` 添加临时 `COLLATE`，因为其他跨表字符串比较仍可能失败。
- 不修改生产数据库或服务器默认排序规则，因为影响范围超出本次发布。
- 不改写已经存在的生产业务表；本次迁移只创建尚不存在的新表。

## 兼容边界

- 新组织权限表与现有生产库、工作流表统一使用 `utf8mb4_unicode_ci`。
- SQL 继续保持可重复执行；`CREATE TABLE IF NOT EXISTS` 不重建或删除已有表。
- 不改变岗位、权限、审批流、人员映射或数据迁移规则。
- 外聘法务顾问截止日期和指定处理人仍必须由管理员确认，预检不得猜测。

## 验证

新增静态迁移回归测试，要求统一组织迁移中的每个
`ENGINE=InnoDB DEFAULT CHARSET=utf8mb4` 表都显式包含
`COLLATE=utf8mb4_unicode_ci`。

修复后执行：

1. 后端完整测试。
2. 前端完整测试和生产构建。
3. 重新提交并推送 GitHub `main`。
4. 按新提交号重新生成发布工件和生产备份。
5. 在与生产库字符集和排序规则一致的临时数据库中重新执行三条 SQL、目录初始化和人员迁移预览。

## 发布门禁

只有迁移 SQL 成功且人员迁移预览不存在未解决记录时，才允许继续生产应用。
任何 `unresolved`、`needs_designation`、`invalid_state` 或 SQL 错误都会停止发布，
保持当前生产版本在线。
