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
- **数据库已于 2026-07-13 补齐到最新 schema**:曾因生产库停留在 7-02 初版(缺 `biz_finance_config`/`biz_financial_metrics`/`biz_project_metrics` 表、`biz_channel_data.mapping` 列、`sys_user.signature` 仅 TEXT)导致 `/operation/financial` 等接口 500。已 `ALTER` 补列 + 加宽 signature + `python -m app.db.init_db`(create_all 建缺失表)修复。
- ⚠️ **每次上传新代码后,若涉及新表/新列,必须同步升级生产库**(跑对应 migration 或 `init_db`),否则接口 500。更新流程里别忘了这一步。

## 大屏地图「数据驱动 + 上传即上屏」(本轮)
目标:大屏天眼地图不再用硬编码点位,改为由数据库项目数据自动驱动;上传统计表后自动上屏。
1. **底图离线根因修复**:`ScreenMap.vue`/`ChinaMapChart.vue` 原先运行时从阿里云公网 CDN 拉 GeoJSON,ECS/内网拉不到 → "地图资源离线"。已把底图下载到 `frontend/public/geo/china.json` **本地自托管**(打包进 `dist/geo/`,nginx 同源 `/geo/china.json` 直服);仍保留阿里云 URL 作二级兜底。
2. **城市自动解析(零依赖 gazetteer)**:`services/geo_gazetteer.py` 内置「城市/省 → 经纬度」词典 + `resolve_city()` 按最长子串匹配(如"泉州欧乐堡"→泉州)。**不依赖在线地理编码 API、不引 pypinyin**,与 captcha/redis 的离线兜底哲学一致。含 4 直辖市+省会+主要地级市,并补了欧乐堡品牌县级基地(齐河/乐陵/青州/蓬莱)。解析不到不阻断入库(city 留空)。
3. **入库**:`biz_project_metrics` 增列 `city/province/lng/lat`;`project_etl.upsert_projects` 上传时自动回填坐标。
4. **点位接口**:`GET /operation/projects/geo?hub=山东省` 按城市聚合(同城多项目合并、金额相加、项目名收集),返回 `points[]` + `version`(项目数+投入合计的数据指纹)+ `matched/unmatched`。
5. **前端联动**:`ScreenMap.vue` 自取该接口(不再吃 DataScreen 传的 mock),飞线线宽/透明度按投入金额缩放,省级填色按点位聚合;**每 30s 轮询,version 变化即重绘 → 上传后 30s 内自动上屏**。空数据时提示去经营页上传。
- ⚠️ **本轮新增了列**:生产库上传新代码后必须跑 `backend/migrations/20260713_project_geo.sql`(幂等,可重复执行);跑完**重新上传一次统计表**回填历史项目坐标(或对已有行执行 resolve_city 回填)。

## 导航重构与权限约定(2026-07-14)
- **菜单标题**:首页→战略总览、经营数据→经营数据中心、渠道集成→渠道业务管理、发票管理→智慧财务管理、客户档案→客户档案库;合同管理 + 审批中心合并为一级「经营合规管理」下的两个子菜单;用户管理保留。
- **合并菜单用「分组渲染」而非路由嵌套**:`router/index.js` 给 contract/approval 打 `meta.group='经营合规管理'`(+`groupIcon`);`layout/index.vue` 的 `menus` computed 按 `meta.group` 归组,渲染成 `el-sub-menu`。**URL 仍是 `/contract`、`/approval` 不变**,不破坏任何跳转/权限;改菜单只动 `meta.title`/`group`。
- **仅超管可见/可访问**:route 上打 `meta.requiresSuperuser: true`(用户管理已用)。双保险:①`layout/index.vue` 菜单过滤 `!requiresSuperuser || isSuperuser` 隐藏;②`permission.js` 路由守卫拦截直访 URL。新增"仅超管页面"照此约定即可,勿再滥用 `roles`。
- **自助改登录信息**:`PUT /users/me/username`(schema `UsernameChange`,需当前密码确认、账号唯一);JWT 的 `sub` 是用户 **id**,改用户名**不掉线**。前端在「个人设置」页,与「修改密码」并列。

## 客户 AI 尽职调查(2026-07-14)
客户档案页每行「AI调研」按钮 → 弹窗上传准入资料(PDF/Docx)→「生成调研报告」。
- **链路**:上传即解析(`services/customer_research.py`:pypdf 逐页 / python-docx;正则抽取信用码/注册资本/经营范围等)→ 生成时融合内部文本 + 博查 Web 搜索外部资讯 → DeepSeek 综合出四段报告(基础概况/经营分析/外部舆情/AI风险预警)+ 合作建议(优先/谨慎/严禁)+ 来源标注。
- **两级降级(接口永不 500)**:无 `DEEPSEEK_API_KEY`/失败 → 规则引擎兜底成文;无 `SEARCH_API_KEY`/失败 → 跳过联网,外部舆情段标注"未联网核实"。
- **⚠️ DeepSeek 不能自己联网**:外部资讯必须由独立搜索 API 提供。当前用**博查 Bocha**(`api.bochaai.com`,国内 ECS 可直连),`.env` 配 `SEARCH_API_KEY=<博查key>` 即启用;留空则外部舆情降级。**生产与本地 `.env` 均已配好博查 key,联网已启用**(实测 ECS 可直连、返回 8 条资讯);轮换 key 只需替换该值重启,无需改码。诉讼/征信权威数据需专门数据源(天眼查/裁判文书),通用搜索只给公开网页舆情(会混入股吧言论/同名公司等噪声,模型会标注权威性),报告已如实标注。
- 🔑 两个 key(DeepSeek、博查)曾在对话中暴露,建议适时到各自控制台轮换。
- **新表**:`biz_customer_material`(逐页文本+关键信息)、`biz_customer_research`(四段+建议+来源)。原始文件存 `backend/uploads/customer_{id}/`(已 gitignore;生产 www-data 可写)。
- **新依赖**:`pypdf`、`python-docx`(仅支持 .pdf/.docx;扫描件图片型 PDF 需 OCR,不支持)。
- **接口**:`GET/POST /customers/{cid}/materials`、`DELETE .../{mid}`、`GET .../{mid}/download`、`POST/GET /customers/{cid}/research`(所有登录用户可用)。
- ⚠️ 生产上线后须跑 `20260714_customer_research.sql`(或 `create_all`)建表 + `pip install -r requirements.txt` 装新依赖 + 建 `uploads/` 目录授权 www-data。

## 本轮迭代(2026-07-15):去演示化 + 客户资料增强 + 合同全生命周期
> 详见 `需求规格说明书.md` 附录 D。均已构建并部署生产。
1. **客户 AI 尽调**:新增 `.xlsx` 解析(`services/customer_research.py::parse_excel_to_text`,openpyxl 转 Markdown 表,零新增依赖);**批量上传**(上传接口 `files: list[UploadFile]`,逐个校验、单失败不阻断,返回 `{succeeded,failed,warnings}`)。术语「尽职调查报告」→「分析报告」。
2. **去演示化**:登录页删除「演示账号」提示块(安全);各处「(演示)」文案清理。
3. **导航**:「智慧财务管理」改为可折叠菜单组 = 资金管理(存根页)+ 发票管理;路由 `/finance/fund`、`/finance/invoice`,旧 `/invoice` 重定向。
4. **角色与权限**:新增 `legal_counsel`(法律顾问,仅可访问「合同管理/审批中心」,前端菜单+守卫双保险);重命名(只改显示名、值不变):`risk_auditor`→投资公司法务风控、`finance_reviewer`→投资公司财务复核、`invest_director`→投资公司分管领导。
5. **合同全生命周期**:审批链改为 **5 节点**(`APPROVAL_CHAIN`:业务经办→供管公司负责人→法律顾问→投资公司法务风控→投资公司分管领导);审批意见沿用 `biz_approval.comment`(未加表/列);`biz_contract` **新增列** is_internal/subject/currency/payment_terms/attachment_name/attachment_stored;**合同附件真实上传下载** `POST/GET /contracts/{id}/attachment`(落盘 `uploads/contract_{id}/`);打印改为「法律文件审批表」(模板 `合同打印模板.docx`,4 意见栏按角色回填);合同台账「生成合同台账」→ 导出 CSV。
- ⚠️ **在途合同**:审批链由 7 级换 5 节点,旧「审批中」合同 `current_step` 可能错位,建议重新提交。

## 数据库迁移(新库/换机必跑)
`init.sql` 建基础表;`python -m app.db.init_db` 建表+种子;运行库补丁按序执行 `backend/migrations/` 下:
`20260710_commercial_data_link.sql`、`20260710_financial_metrics.sql`、`20260710_project_metrics.sql`、`20260713_project_geo.sql`、`20260714_customer_research.sql`、`20260715_contract_lifecycle.sql`(合同全生命周期新列,幂等)、`20260716_module_refactor.sql`(社会信用代码/合同类型文本化/渠道 biz_type,幂等)、`20260717_rename_admin.sql`(admin 显示名→信息维护,幂等)。

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
