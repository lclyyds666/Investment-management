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

## 第 1 周「基础闭环与安全底座 (P0)」已完成(本轮)
1. **认证安全**:
   - 图形验证码:`services/captcha.py` 生成 SVG(零依赖,对齐 Mock 签名思路),`GET /auth/captcha` 返回 `{captcha_id, image, ttl}`;登录需回传 `captcha_id + captcha_code`,一次性消费。
   - 暴力破解防护:`services/login_guard.py`,连续失败 5 次锁定 30 分钟;锁定窗口内密码正确也拒绝(429)。
   - **KV 存储 `core/store.py`**:验证码/失败计数存这。配了 `REDIS_URL` 且 redis 可连 → Redis;否则**自动回退进程内存**(单机开发不装 Redis 也能跑,对齐 DeepSeek 回退哲学)。
   - 开关见 `config.py`/`.env`:`CAPTCHA_ENABLED`(联调/Swagger 调试可临时设 false)、`LOGIN_MAX_FAILURES`、`LOGIN_LOCK_MINUTES`、`PASSWORD_MIN_LENGTH`、`DEFAULT_PASSWORD`。
2. **用户管理完整 CRUD**:`endpoints/user.py`。列表支持 `keyword/role/is_active` 筛选;创建/编辑/删除/启停用/重置密码均 `require_superuser`(见 `deps.py`);本人改密 `PUT /users/me/password`。护栏:不能删/停用自己、不能撤下最后一个超管。前端 `views/system/users.vue` 已重构为完整 CRUD(菜单更名「用户管理」,增删改按钮仅超管可见);个人中心 `views/profile/index.vue` 加了修改密码卡片。
3. **敏感数据脱敏**:`core/masking.py` `mask_phone`(138****5678),客户**列表**输出脱敏,详情页仍返回明文供编辑。
4. **未新增数据库列**:User 模型原有字段已够,本周无需迁移;`redis` 已加入 `requirements.txt`(可选,缺失自动回退内存)。

## 生产部署现状(2026-07-13 已上线)
- 服务器:阿里云 ECS `39.107.52.146`(Ubuntu 22.04),部署目录 `/opt/sd-scm`(属主 www-data)。
- 架构:Nginx:80(静态 `frontend/dist` + 反代 `/api` → 127.0.0.1:8000)→ Uvicorn(systemd `sd-scm-backend`,2 workers)→ MySQL;**Redis 已装**(仅监听 127.0.0.1,`REDIS_URL=redis://127.0.0.1:6379/0`)。
- **多 worker 必须用 Redis**:验证码/防爆破计数跨 worker 共享,靠的就是 Redis;内存兜底只在单进程有效。
- `.env` 已含第1周安全项(REDIS_URL/CAPTCHA_*/LOGIN_*),`DEBUG=false`、`SECRET_KEY` 已是自定义。改 .env 前会自动 `.bak` 备份。
- **`/opt/sd-scm` 不是 git 仓库**:更新代码走「本地 `npm run build` → tar over ssh 传 `backend/app`+`requirements.txt`+`frontend/dist`」;传完 `chown -R www-data:www-data`、`.venv/bin/pip install -r requirements.txt`、`systemctl restart sd-scm-backend`、`nginx -t && systemctl reload nginx`。
- SSH 已配本机免密公钥(`~/.ssh/id_ed25519`),后续可直接 `ssh root@39.107.52.146` 免密操作。
- ⚠️ 上线后务必:①把所有默认账号密码 `123456` 改掉;②考虑轮换服务器 root 密码(曾在对话中出现)。

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
