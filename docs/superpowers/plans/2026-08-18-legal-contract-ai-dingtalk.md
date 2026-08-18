# 法务合同管理、AI 审查与钉钉预警 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在法务风控侧复用供应链合同管理全部能力，安全启用 DeepSeek 合同审查、法规知识库和生产钉钉预警。

**Architecture:** 合同数据、工作流、附件、法规库和 API 保持单一来源，法务应用只新增受双重权限保护的路由与导航。后端对 AI 审查和文件下载统一补齐合同数据范围校验，生产密钥仅写服务器 `.env`。

**Tech Stack:** Vue 3、Vue Router、Pinia、Element Plus、Vitest、FastAPI、SQLAlchemy、pytest、DeepSeek OpenAI-compatible API、钉钉机器人、systemd、Nginx。

## Global Constraints

- 法务合同入口必须复用 `frontend/src/views/contract/index.vue` 和现有 `/api/v1/contracts`，不得复制合同模型、表或工作流。
- 路由路径固定为 `/investment/legal-risk/contracts`，菜单名称固定为“合同管理”。
- 入口必须同时要求 `invest.legal.cases` 资源和 `supply.contract.view` 权限。
- AI 审查、合同附件和法律文件下载必须执行 `_ensure_contract_visible` 数据范围校验。
- AI Markdown 必须通过 `renderSafeMarkdown` 渲染，不得直接使用 `marked.parse` 配合 `v-html`。
- DeepSeek API Key、钉钉 Webhook 和 Secret 不得进入 Git、发布包、测试输出或日志。
- DeepSeek 失败时保留现有规则引擎降级；钉钉失败时保留投递记录和有界重试。

---

### Task 1: 法务合同入口与安全 AI 展示

**Files:**
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/router/routes.test.js`
- Modify: `frontend/src/layout/InvestmentLayout.vue`
- Create: `frontend/src/layout/InvestmentLayout.test.js`
- Modify: `frontend/src/views/contract/index.vue`
- Modify: `frontend/src/views/contract/index.test.js`

**Interfaces:**
- Consumes: `RESOURCE_CODES.INVEST_LEGAL_CASES`、`portalStore.hasPermission(code)`、`renderSafeMarkdown(source)`。
- Produces: 路由 `LegalRiskContracts`，路径 `/investment/legal-risk/contracts`，复用合同管理组件。

- [ ] **Step 1: 写路由和导航失败测试**

在 `routes.test.js` 增加：

```js
const route = router.resolve({ name: 'LegalRiskContracts' })
expect(route.path).toBe('/investment/legal-risk/contracts')
expect(route.meta.resource).toBe('invest.legal.cases')
expect(route.meta.permission).toBe('supply.contract.view')
```

在 `InvestmentLayout.test.js` 使用可控的 `portalStore.hasResource` 和 `portalStore.hasPermission`，分别断言有合同权限时显示“合同管理”，无 `supply.contract.view` 时隐藏。

- [ ] **Step 2: 运行测试确认失败**

Run: `npm test -- --run src/router/routes.test.js src/layout/InvestmentLayout.test.js`

Expected: FAIL，原因是 `LegalRiskContracts` 和合同菜单尚不存在。

- [ ] **Step 3: 实现法务路由和菜单**

在投资公司子路由新增：

```js
{
  path: 'legal-risk/contracts',
  name: 'LegalRiskContracts',
  component: () => import('@/views/contract/index.vue'),
  meta: {
    title: '合同管理',
    company: COMPANY_CODES.INVESTMENT,
    resource: RESOURCE_CODES.INVEST_LEGAL_CASES,
    permission: 'supply.contract.view'
  }
}
```

在 `InvestmentLayout.vue` 的“案件管理”后加入 `DocumentChecked` 图标菜单，并让 `menus` 同时过滤 `item.resource` 与可选 `item.permission`。

- [ ] **Step 4: 写 AI Markdown 安全渲染失败测试**

在合同页面测试中设置包含 `<img onerror>`、链接和加粗文本的 AI Markdown，断言结果保留风险文字和 `<strong>`，但不包含 `img`、`onerror`、`href`。

- [ ] **Step 5: 替换不安全 Markdown 渲染**

删除合同页面对 `marked` 的直接使用，改为：

```js
import { renderSafeMarkdown } from '@/utils/safeMarkdown'
const aiHtml = computed(() => renderSafeMarkdown(aiResult.value?.markdown || ''))
```

- [ ] **Step 6: 运行前端定向测试**

Run: `npm test -- --run src/router/routes.test.js src/layout/InvestmentLayout.test.js src/views/contract/index.test.js src/utils/safeMarkdown.test.js`

Expected: PASS。

- [ ] **Step 7: 提交任务**

```bash
git add frontend/src/router/index.js frontend/src/router/routes.test.js frontend/src/layout/InvestmentLayout.vue frontend/src/layout/InvestmentLayout.test.js frontend/src/views/contract/index.vue frontend/src/views/contract/index.test.js
git commit -m "feat: expose contract management in legal risk"
```

### Task 2: 合同 AI 与文件访问范围加固

**Files:**
- Modify: `backend/app/api/v1/endpoints/contract.py`
- Modify: `backend/tests/test_company_permissions.py`

**Interfaces:**
- Consumes: `_get_contract_or_404(db, contract_id)`、`_ensure_contract_visible(db, contract, current_user)`。
- Produces: AI 审查、附件下载和法律文件下载与合同列表/详情相同的数据范围行为。

- [ ] **Step 1: 写越权访问失败测试**

为仅有 `assigned` 合同查看/导出权限的法律顾问创建一个未被指定的合同，断言以下请求均返回 `403`：

```python
self.client.post(f"/api/v1/contracts/{hidden_id}/ai-review")
self.client.get(f"/api/v1/contracts/{hidden_id}/attachment")
self.client.get(f"/api/v1/contracts/{hidden_id}/legal-doc")
```

同时为被指定合同保留成功路径或进入业务级 `404`，证明校验只拦截越权，不改变文件不存在语义。

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_company_permissions.py -q`

Expected: FAIL，未指定合同的 AI/文件端点没有统一执行可见范围校验。

- [ ] **Step 3: 实现统一可见范围校验**

三个端点都注入 `current_user: User = Depends(...)`，读取合同后立即执行：

```python
contract = _get_contract_or_404(db, contract_id)
_ensure_contract_visible(db, contract, current_user)
```

保留现有权限 Guard：AI 使用查看权限，文件使用导出权限。

- [ ] **Step 4: 运行后端定向测试**

Run: `python -m pytest tests/test_company_permissions.py tests/test_dingtalk.py -q`

Expected: PASS。

- [ ] **Step 5: 提交任务**

```bash
git add backend/app/api/v1/endpoints/contract.py backend/tests/test_company_permissions.py
git commit -m "fix: enforce contract scope on reviews and downloads"
```

### Task 3: 运维说明、全量验证与生产启用

**Files:**
- Modify: `docs/legal-risk-operations.md`

**Interfaces:**
- Consumes: `/opt/sd-scm/backend/.env`、`DingTalkClient.send_test`、`/api/v1/health`。
- Produces: 不含真实密钥的 AI/钉钉配置与验收步骤。

- [ ] **Step 1: 更新运维说明**

增加以下不含真实值的生产配置和验收命令：

```dotenv
DEEPSEEK_API_KEY=实际密钥
DINGTALK_LEGAL_ALERT_ENABLED=true
DINGTALK_LEGAL_ALERT_WEBHOOK=实际Webhook
DINGTALK_LEGAL_ALERT_SECRET=实际Secret
```

说明部署前备份 `backend/uploads/contract_*`、`backend/uploads/knowledge_base`、`backend/uploads/legal-risk` 和 `.env`，并验证法务合同路由、DeepSeek `engine=deepseek` 与钉钉测试消息。

- [ ] **Step 2: 运行全量验证**

Run: `python -m pytest`

Expected: 后端全量 PASS。

Run: `npm test -- --run`

Expected: 前端全量 PASS。

Run: `npm run build`

Expected: 生产构建成功，仅允许已有 Rollup 体积/PURE 注释警告。

- [ ] **Step 3: 提交运维说明**

```bash
git add docs/legal-risk-operations.md
git commit -m "docs: add legal contract production checks"
```

- [ ] **Step 4: 审查、推送和部署**

执行最终代码审查和 `git diff --check`；推送当前提交到 `main`。生产先备份数据库、上传目录、`.env`、后端、前端和 `REVISION`，再原子切换后端 `app` 与前端 `dist`。

- [ ] **Step 5: 安全写入生产密钥并验收**

在服务器本地更新 `.env`，禁止在命令输出显示值；重启 `sd-scm-backend`。验证：

```bash
curl -fsS http://127.0.0.1/api/v1/health
systemctl is-active sd-scm-backend nginx sd-scm-legal-alert-scan.timer sd-scm-legal-alert-retry.timer
```

使用一个现有合同执行 AI 审查并确认 `engine=deepseek`，调用 `DingTalkClient.send_test` 并确认 `status=sent`，最后核对生产 `REVISION` 与远端 `main`。
