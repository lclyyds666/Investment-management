# CLAUDE.md — 项目现状与协作须知

> 本文件供 Claude Code 在新会话/新机器上快速接手。人也可当作项目速览。

## 项目概览
山东出版供应链管理公司业务平台,前后端分离。
- 前端:Vue 3 + Vite + Element Plus + ECharts(`frontend/`,开发端口 5173,`/api` 代理到后端 8000)
- 后端:FastAPI + SQLAlchemy 2.0(`backend/`,端口 8000)
- 数据库:MySQL 8.0,库名 `sd_publish_scm`
- 7 级审批角色 + 合同审批流 + 经营看板 + 数据大屏(`/screen`)

## ⚠️ 启动与环境的关键约定
- **后端必须在 `backend/` 目录下启动**:`cd backend && uvicorn app.main:app --reload`。
  pydantic 按当前工作目录找 `.env`,在别处启动会报 `Access denied ... using password: NO`。
- 依赖装在 `backend/.venv`(不是仓库根的 `.venv`)。
- 敏感信息在 `backend/.env`(已 gitignore):`DB_PASSWORD`、`DEEPSEEK_API_KEY`。照 `backend/.env.example` 重建。
- 真实数据文件 `*.xlsx`/`*.csv` 已 gitignore,不在仓库,需单独拷贝。

## 已完成的「商用级数据打通」(本轮工作)
1. **签名 / 审批流**:签名存 `sys_user.signature`,审批时快照进 `biz_approval.signature_snapshot`,`ContractDetailDrawer.vue` 打印审批单动态渲染;签名列已加宽为 MEDIUMTEXT。大屏审批流跑马灯去 mock、读真实 pending 合同、20s 轮询。
2. **渠道联动**:`biz_channel_data` 加 `mapping` 列;`services/channel_etl.py` 按映射把渠道回传数据(每渠道独立业务线、覆盖式幂等)汇入 `biz_operation_data`,联动首页/大屏。
3. **AI 智能体(DeepSeek)**:`services/ai_agent.py` 走 OpenAI 兼容协议,把真实经营/财务聚合作为 Context;**无 Key 或调用失败自动回退规则引擎,接口永不 500**。配置见 `config.py` 的 `DEEPSEEK_*`。
4. **财务经营指标(对账单)**:`biz_financial_metrics` + `services/financial.py`,解析抖音/美团/携程对账单 xlsx 提取「应扣出版预付」等,接口 `POST /operation/financial/upload`。
5. **供管公司项目经营指标(当前经营看板主数据源)**:`biz_project_metrics` + `services/project_etl.py`,解析「年度项目投入及回款收益统计表」Sheet2(单位万元→元),接口 `POST /operation/projects/upload`。
   - 映射:投入金额→现存业务规模;回款小计→已实现业务规模;实现毛利→已实现业务毛收入;收益率取表值(汇总按投入加权);资金占用=投入−回款;可用资金=手工录入(`biz_finance_config.available_funds`,`PUT /operation/financial/available`)。
   - 经营页 `views/operation/index.vue` 已重构为**项目维度**;大屏指标卡同源(读 `GET /operation/financial`)。

## 数据库迁移(新库/换机必跑)
`init.sql` 建基础表;`python -m app.db.init_db` 建表+种子;运行库补丁按序执行 `backend/migrations/` 下:
`20260710_commercial_data_link.sql`、`20260710_financial_metrics.sql`、`20260710_project_metrics.sql`。

## 待办 / 注意
- **DeepSeek 账户余额**:Key 有效但曾余额不足会回退规则引擎;充值后无需改码自动切真实模型。
- **可用资金**当前为 0(显示「—」),等公司总资金池数字确定后在经营页录入。
- 磁盘上另有一份**旧副本 `D:\1`**(非本仓库),勿混用;一切以本仓库(git 根)为准。

## 常用验证
```bash
cd backend && .venv/Scripts/python.exe -c "from app.main import app; print(len(app.routes))"
# 本机 curl 走了代理会 502,加 --noproxy '*'
curl -s --noproxy '*' http://127.0.0.1:8000/api/v1/health
```
