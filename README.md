# 山东出版供应链管理公司业务平台

企业级业务中台,前后端分离。覆盖 **合同全生命周期审批、业务审批(双工作流)、AI 合同校对、文旅业务景区核销台账、经营数据看板、数据大屏、渠道业务、智慧财务、客户 AI 尽调、用户与权限** 等模块。

| 层 | 技术 |
| --- | --- |
| 前端 | Vue 3 + Vite + Element Plus + ECharts |
| 后端 | Python FastAPI + SQLAlchemy 2.0 |
| 数据库 | MySQL 8.0(库名 `sd_publish_scm`) |
| 缓存 | Redis(可选;缺失自动回退进程内存) |
| AI | DeepSeek(OpenAI 兼容协议)+ 博查 Web 搜索 |

---

## 📊 任务进度(需求实现进度)

> 数据源:`需求规格说明书.md` 附录 A/B/C/D。图例:✅ 已实现　🟡 部分实现 / 与商用有差距　❌ 未实现 / 未开工　🔒 甲方依赖(接口权限未下发)。
> **约定:每次功能有更新,必须同步更新本章节**(模块状态 + 阶段勾选 + 文末「迭代日志」追加一行)。最后更新:**2026-07-21**。
> 粗略完成度:P0 核心约 **80%**;整份规格(含 P1/P2/小程序)约 **55%**。

### 模块实现状态

| 模块 | 优先级 | 状态 | 说明 / 主要缺口 |
| --- | --- | --- | --- |
| 认证安全 | P0 | ✅ | 密码登录 + JWT + 图形验证码 + 防爆破(Redis/内存兜底)。缺:忘记密码、Token 刷新 |
| 用户与权限 | P0 | ✅ | 完整 CRUD + 8 角色 + 本人改密改名 + 手机号脱敏 + 「仅超管」双保险 |
| 电子签名 | P0 | ✅ | 上传 / 审批快照附签 / 打印渲染。缺:水印、超管重置签名 |
| 合同全生命周期 | P0 | ✅ | 5 节点审批流 + 附件真实上传下载 + 台账导出 CSV + 「法律文件审批表」打印。缺:撤回/转交/加签/会签/时限/归档 |
| 业务审批(双工作流) | P0 | ✅ | 付款审批单(7 节点,金额大小写转换)+ 业务审批单(5 节点)+ 按模板打印 + **AI 合同校对** |
| 财务管理(进/出账台账) | P0 | ❌ | **主要缺口**:仅有对账单 xlsx 解析→指标聚合,尚无系统内进账/出账/对账台账 |
| 发票管理 | P1 | ✅ | CRUD + 关联合同 + 开票确认 + 统计 + 作废。缺:打印、税号验证、电子发票 |
| 客户档案 + AI 尽调 | P1 | ✅ | CRUD + 脱敏 + PDF/Word/Excel 批量上传 → DeepSeek 分析报告(两级降级)。缺:评级、标签 |
| 经营数据 & 大屏 & AI | P1 | 🟡 | 项目看板 + 数据驱动地图飞线 + 真实 DeepSeek 诊断。差距:省份下钻仍 mock、靠轮询非推送、导出报表未做 |
| 渠道业务 | P0 | 🟡🔒 | CRUD + CSV 导入/回传 + 列映射汇入经营表。缺:真实 OTA(美团/抖音)对接🔒、账号密码加密(现明文) |
| 文旅业务(景区核销台账) | — | ✅ | 景区卡片 Grid → 详情(经营数据卡 + 平台入口 + 折叠台账);Excel 上传;按 `scenic_id` 严格数据隔离 |
| 明暗双主题切换 | — | ✅ | 明亮/暗黑切换 + localStorage 持久化;`--chrome-*` 外壳变量;大屏/登录页恒定深色 |
| 操作审计 | P1 | ✅ | 登录日志 + 写操作中间件自动留痕(POST/PUT/DELETE)+ 导出类 GET;按用户/模块/动作/状态/时间筛选查询 + CSV 导出;仅超管可见 |
| 系统配置 / 监控 / 定时任务 / 消息通知 | P2 | ❌ | 参数/字典/公告/部门/岗位、服务监控、缓存监控、定时同步、WebSocket 推送均未开工 |
| 传输加密(RSA+AES)、Docker Compose | P2 | ❌ | 未开工 |
| 小程序端 | — | ❌ | 移动审批 / 待办 / 查看 / 个人中心整套未开工 |

### 阶段计划进度(附录 B · 四周迭代)

| 阶段 | 内容 | 进度 |
| --- | --- | --- |
| 第 1 周 | 基础闭环与安全底座(用户 CRUD / 验证码 / 防爆破 / 脱敏) | ✅ 已完成 |
| 第 2 周 | 财务闭环 + 操作审计 | 🟡 审计仅审批记录、进出账台账未做 |
| 第 3 周 | 渠道对接 + 合同增强 | 🟡 合同增强大部完成;OTA 对接 🔒 待甲方接口 |
| 第 4 周 | 小程序端 + 系统模块 + 联调上线 | ❌ 系统模块/小程序未开工(生产环境已上线运行) |

### 迭代日志(每次更新在此追加一行)

| 日期 | 本轮内容 | 部署 |
| --- | --- | --- |
| 2026-07-10 | 商用数据打通(签名/审批快照、渠道联动、真实 DeepSeek、财务/项目看板) | 生产 ✅ |
| 2026-07-13 | 大屏地图数据驱动 + 上传即上屏;生产库补齐 schema | 生产 ✅ |
| 2026-07-14 | 认证安全 P0(验证码/防爆破)+ 用户完整 CRUD + 脱敏 + 导航重构 + 客户 AI 尽调 | 生产 ✅ |
| 2026-07-15 | 去演示化 + 客户资料增强(xlsx/批量上传)+ 合同全生命周期(5 节点/附件/打印) | 生产 ✅ |
| 2026-07-16 | 业务审批双工作流(付款单 7/业务单 5)+ AI 合同校对 + 法规知识库 | 生产 ✅ |
| 2026-07-17~18 | 全局命名规范 + 文旅业务景区数据隔离 + 信息维护角色 | 生产 ✅ |
| 2026-07-20 | 门票台账非阻塞解析 + 并发闸 + 服务器扩容方案文档 | 生产 ✅ |
| 2026-07-21 | 景区详情页重构(经营数据卡 + 平台入口放大改名 + 台账折叠)+ **明暗双主题切换** | 生产 ✅ |
| 2026-07-22 | 核销台账期次递推(出版应得=到账−佣金、景区待核销滚动余额)+ 对账明细单文件流(源文件预览/下载、待确认仅展示本期、去覆盖按钮、费率移入编辑弹窗、列改名/隐藏付款日期)+ **审批导航角标**(/approval/pending-count,合同/业务审批按角色显示待办数) | 生产 ✅ |
| 2026-07-23 | **操作审计**(登录日志 + 写操作中间件自动留痕 + 查询筛选 + CSV 导出,仅超管);导航新增「系统管理」组(用户管理 + 操作审计) | 生产 ✅ |
| 2026-07-24 | **景区酒店平台核销台账**(抖音/美团/携程多平台;一文件=一期多平台行;核销=基数×90%、服务费=间夜×44、结算=核销+服务费;付款金额隐藏留存、待核销按平台滚动、本期合计行;真实台账 6 期反推验证) | 待部署 🟡 |
| 2026-07-25 | **前端体验优化 · 通用列表组件 `ProTable`**(配置化列 + 关键词搜索 + 客户端分页 + **首屏骨架屏** + **加载失败重试态** + 空态 + `#prepend` 父控筛选插槽,`defineExpose(reload)`);铺开 3 页:`invoice`(统计卡 `:xs/:sm` 响应式 + 税号校验)、`customer`(社会信用代码/电话格式校验)、`users`(保留服务端角色/状态筛选 + 补分页/骨架/空态、成功提示文案统一);contract/approval 待评估(多表/多 Tab,拟接服务端分页) | 生产 ✅ |

---

## 一、目录结构

```
Investment-management/
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── api/v1/endpoints/    # 路由:auth / user / contract / customer / channel / invoice / operation ...
│   │   ├── core/               # 配置、枚举(角色/审批链)、安全、脱敏、KV 存储、验证码
│   │   ├── models/             # SQLAlchemy ORM 模型
│   │   ├── schemas/            # Pydantic 出入参模型
│   │   ├── services/           # 业务服务:AI 代理 / 渠道 ETL / 财务 / 客户尽调 / 地理词典 ...
│   │   └── db/                 # 会话、Base、init_db(建表+种子)
│   ├── migrations/             # 运行库增量迁移 SQL(按序执行)
│   ├── uploads/                # 上传文件落盘(gitignore)
│   ├── requirements.txt
│   └── .env                    # 密钥配置(gitignore,照 .env.example 重建)
├── frontend/                   # Vue3 前端
│   ├── src/
│   │   ├── views/              # 页面:dashboard / operation / contract / approval / customer / channel / invoice / finance / system ...
│   │   ├── components/         # 复用组件(合同详情抽屉、客户 AI 尽调弹窗 ...)
│   │   ├── router/、permission.js  # 路由与守卫(角色/超管拦截)
│   │   ├── store/、api/、constants/ # Pinia / 接口封装 / 业务常量(角色、审批链)
│   │   └── layout/             # 侧边栏(按 meta.group 分组渲染)
│   └── public/geo/china.json   # 大屏地图底图(本地自托管)
├── deploy/                     # 生产部署产物(nginx.conf、systemd service)
├── init.sql                    # 基础建表脚本
├── 合同打印模板.docx            # 「法律文件审批表」打印模板(参考)
├── CLAUDE.md                   # 项目现状与协作须知(新会话/换机快速接手)
├── 需求规格说明书.md            # 需求 + 实现状态对照(见文末附录)
└── README.md
```

---

## 二、核心功能模块(当前状态)

| 模块 | 能力 |
| --- | --- |
| **认证安全** | 密码登录 + JWT;图形验证码(SVG 零依赖,一次性消费);暴力破解防护(失败 5 次锁 30 分钟,Redis→内存兜底) |
| **用户与权限** | 用户完整 CRUD(超管);本人改密/改登录名;手机号脱敏;8 角色 + 「仅超管」页面双保险 |
| **合同全生命周期** | 新建(申请部门/编号/名称/类型/是否内部/标的/签订日期/客户/金额/币种/付款条件/**附件真实上传**);5 节点审批流;**合同台账导出 CSV**;**「法律文件审批表」打印**;**PDF 附件预览/下载**(任意登录用户可查看) |
| **业务审批**(原「审批中心」) | **两套独立工作流**:①业务付款审批单(7 节点,含付款金额大小写自动转换/开户行/银行账号)②业务审批单(5 节点);列表统一列(申请日期/客户/业务类型/合同编号/付款金额);**按原始 xlsx 模板还原打印**;**AI 合同校对**(附件 ⇄ 合同库原件文本比对,DeepSeek + 规则兜底,聚焦正文、排除落款/盖章/签字页) |
| **文旅业务**(渠道业务下) | 入口页景区卡片 Grid(每行 3 个)→ 景区详情(平台入口 + **核销数据台账**);**Excel 上传/清空/预览**;**按 `scenic_id` 严格数据隔离**(接口只返本景区数据,`WHERE scenic_id`) |
| **客户档案库** | 增删改查 + 手机号脱敏;**AI 尽职调查**(PDF/Word/Excel **批量上传** → 解析 → 融合博查外部资讯 → DeepSeek 生成分析报告,两级降级不 500) |
| **经营数据 & 大屏** | 项目维度经营看板;数据大屏(KPI/趋势/**数据驱动地图飞线**/省份联动/审批跑马灯/AI 雷达) |
| **渠道业务** | 渠道 CRUD;CSV 导入/回传;列映射汇入经营表,联动看板/大屏 |
| **智慧财务** | 菜单组:资金管理(建设中)+ 发票管理;对账单 xlsx 解析 → 财务指标聚合 |
| **用户下拉菜单** | 个人信息/修改密码/修改用户名/电子签章/退出登录;后三项为 **el-dialog 弹窗**(不切路由,关闭清理状态) |

> 各模块详细实现状态与差距见 `需求规格说明书.md` 附录 A/C/D。

---

## 三、角色与权限

系统共 **8 个角色**(角色值存字符串,重命名只改显示名):

| 角色值 | 显示名 | 说明 |
| --- | --- | --- |
| `business_handler` | 业务经办 | 合同录入与提交 |
| `scm_director` | 供管公司负责人 | 合同审批节点① |
| `legal_counsel` | **法律顾问** | 仅可访问「合同管理 / 审批中心」;合同审批节点② |
| `risk_auditor` | 投资公司法务风控 | 合同审批节点③(原「风控审核」) |
| `invest_director` | 投资公司分管领导 | 合同审批节点④,末级(原「投资公司负责人」) |
| `finance_reviewer` | 投资公司财务复核 | 财务模块(原「财务复核」) |
| `business_reviewer` / `finance_handler` | 业务复核 / 财务经办 | 保留角色,不在合同审批链上 |

**审批链**(顺序即流转顺序,三条互不干扰):

```
① 合同(法律)审批链   业务经办 → 供管公司负责人 → 法律顾问 → 投资公司法务风控 → 投资公司分管领导
② 业务付款审批单(7)   业务经办 → 业务复核 → 财务经办 → 供管公司负责人 → 投资公司法务风控 → 投资公司财务复核 → 投资公司分管领导
③ 业务审批单(5)       业务经办 → 业务复核 → 供管公司负责人 → 投资公司法务风控 → 投资公司分管领导
```

除「业务经办」(提交时自动完成第 0 级并附签)外,其余节点在「业务审批」页均需/可填写审批意见,并自动附加电子签章;末级通过即 `approved`。

> **信息维护**(超管账号身份,`info_maintainer`)不参与签章:上传/维护电子签名的接口与页面均已拦截/隐藏。

---

## 四、本地快速启动

> 前置:Python 3.10+、Node.js LTS、MySQL 8.0。(Redis 可选,不装自动回退内存。)

### 1. 数据库
```bash
mysql -u root -p < init.sql               # 建库建表
```
再按「第五节」执行 `migrations/` 下的增量迁移。

### 2. 后端(⚠️ 必须在 backend/ 目录下启动,否则读不到 .env)
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate                    # Windows;macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                       # 修改 DB_PASSWORD;可选填 DEEPSEEK_API_KEY / SEARCH_API_KEY
python -m app.db.init_db                   # 建缺失表 + 写入 9 个种子账号 + 电子签名
uvicorn app.main:app --reload             # http://127.0.0.1:8000/docs
```

### 3. 前端(另开终端)
```bash
cd frontend
npm install
npm run dev                                # http://localhost:5173  (/api 代理到 8000)
```

### 4. 默认账号(密码均 `123456`,登录后请尽快改密)

| 账号 | 角色 | 账号 | 角色 |
| --- | --- | --- | --- |
| `admin` | 超级管理员 | `scm` | 供管公司负责人 |
| `op` | 业务经办 | `legal` | 法律顾问 |
| `risk` | 投资公司法务风控 | `inv` | 投资公司分管领导 |
| `review` | 业务复核 | `fin` | 财务经办 |
| `finr` | 投资公司财务复核 | | |

---

## 五、数据库与迁移

`init.sql` 建基础表;`python -m app.db.init_db` 用 `create_all` 补齐缺失表并写种子。
**换机 / 生产升级时,按序执行 `backend/migrations/` 下的增量脚本**(均幂等,可重复执行):

```bash
mysql -u root -p sd_publish_scm < backend/migrations/20260710_commercial_data_link.sql
mysql -u root -p sd_publish_scm < backend/migrations/20260710_financial_metrics.sql
mysql -u root -p sd_publish_scm < backend/migrations/20260710_project_metrics.sql
mysql -u root -p sd_publish_scm < backend/migrations/20260713_project_geo.sql
mysql -u root -p sd_publish_scm < backend/migrations/20260714_customer_research.sql
mysql -u root -p sd_publish_scm < backend/migrations/20260715_contract_lifecycle.sql   # 合同全生命周期新列
mysql -u root -p sd_publish_scm < backend/migrations/20260716_knowledge_base.sql       # 法规知识库
mysql -u root -p sd_publish_scm < backend/migrations/20260716_module_refactor.sql      # 社会信用代码/合同类型文本化/渠道 biz_type
mysql -u root -p sd_publish_scm < backend/migrations/20260716_approval_center.sql      # 业务审批双工作流(biz_approval_form/_action)
mysql -u root -p sd_publish_scm < backend/migrations/20260716_scenic_ledger.sql        # 文旅业务景区核销台账(biz_scenic_ledger)
mysql -u root -p sd_publish_scm < backend/migrations/20260717_rename_admin.sql         # admin 显示名→信息维护
mysql -u root -p sd_publish_scm < backend/migrations/20260717_scenic_id_rename.sql     # 景区 scenic_id 与新名对齐(幂等,空表 no-op)
mysql -u root -p sd_publish_scm < backend/migrations/20260718_info_maintainer_role.sql # 信息维护角色
mysql -u root -p sd_publish_scm < backend/migrations/20260720_ticket_ledger.sql        # 门票平台核销业务台账(biz_ticket_ledger)
mysql -u root -p sd_publish_scm < backend/migrations/20260722_ticket_ledger_recurrence.sql # 门票台账期次递推(佣金/付款金额/待核销滚动余额/明细源文件列)
mysql -u root -p sd_publish_scm < backend/migrations/20260723_audit_log.sql             # 操作审计日志表 sys_audit_log
mysql -u root -p sd_publish_scm < backend/migrations/20260724_hotel_ledger.sql          # 景区酒店平台核销台账 biz_hotel_ledger
```

> 新表/新依赖提醒:业务审批打印/签章图嵌入需 **Pillow**;景区台账、对账单等 Excel 解析用 **openpyxl**——升级生产后须 `pip install -r requirements.txt`。

> ⚠️ **每次上传涉及新表/新列的代码后,务必同步升级生产库**(跑对应迁移或 `init_db`),否则接口 500。

---

## 六、生产部署(阿里云 ECS `39.107.52.146` · Ubuntu 22.04)

**架构**:`浏览器 → Nginx:80(静态 dist + 反代 /api) → Uvicorn 127.0.0.1:8000(systemd,2 workers) → MySQL`;Redis 仅监听本地。

- 部署目录 `/opt/sd-scm`(属主 `www-data`);**该目录不是 git 仓库**,靠「本地构建 → tar over ssh」更新。
- 多 worker **必须用 Redis** 共享验证码/防爆破计数;内存兜底只在单进程有效。
- `.env` 内 `DEBUG=false`、`SECRET_KEY` 自定义、`REDIS_URL`/`CAPTCHA_*`/`LOGIN_*`/`DEEPSEEK_*`/`SEARCH_API_KEY` 均已配。

### 首次部署(参考 `deploy/`)
```bash
apt install -y mysql-server nginx python3-venv python3-pip redis-server
mysql -u root -p < /opt/sd-scm/init.sql
cd /opt/sd-scm/backend && python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # 改 DB_PASSWORD / SECRET_KEY(openssl rand -hex 32)/ DEBUG=false
python -m app.db.init_db
cp /opt/sd-scm/deploy/sd-scm-backend.service /etc/systemd/system/
cp /opt/sd-scm/deploy/nginx.conf /etc/nginx/conf.d/sd-scm.conf
chown -R www-data:www-data /opt/sd-scm
systemctl daemon-reload && systemctl enable --now sd-scm-backend
nginx -t && systemctl restart nginx
```

### 日常更新流程(已配本机 SSH 免密)
```bash
# 1) 本地构建前端
cd frontend && npm run build

# 2) 打包并上传(前端 dist + 后端 app + 依赖清单)
tar -czf dist.tgz -C frontend/dist .
tar -czf app.tgz  -C backend app
scp dist.tgz app.tgz root@39.107.52.146:/tmp/

# 3) 服务器:备份→覆盖→授权→(涉及新表则跑迁移)→重启
ssh root@39.107.52.146 '
  cd /opt/sd-scm
  cp -a frontend/dist frontend/dist.bak && cp -a backend/app backend/app.bak
  rm -rf frontend/dist && mkdir frontend/dist && tar -xzf /tmp/dist.tgz -C frontend/dist
  tar -xzf /tmp/app.tgz -C backend
  chown -R www-data:www-data frontend/dist backend/app
  cd backend && .venv/bin/pip install -q -r requirements.txt
  # 若有新迁移:mysql sd_publish_scm < migrations/xxx.sql
  systemctl restart sd-scm-backend
  nginx -t && systemctl reload nginx
'
```

> 更新后浏览器强刷(`Ctrl/Cmd+Shift+R`)或用无痕窗口,避开静态缓存。

---

## 七、GitHub 同步

远程已关联 `origin` → `https://github.com/lclyyds666/Investment-management.git`。

```bash
git add -A
git commit -m "说明本次改动"
git push
```

- `backend/.env`、`*.xlsx`/`*.csv`、`.venv/`、`node_modules/`、`backend/uploads/` 已被 `.gitignore` 排除,不会上传。
- 认证:GitHub 用 **Personal Access Token** 或 `gh auth login`。
- ⚠️ 建议仓库设为 **Private**(含企业业务逻辑)。

---

## 八、环境变量与密钥(`backend/.env`)

照 `backend/.env.example` 重建,关键项:

| 变量 | 说明 |
| --- | --- |
| `DB_PASSWORD` | MySQL 密码 |
| `SECRET_KEY` | JWT 签名密钥,生产必须改随机串 |
| `DEBUG` | 生产设 `false` |
| `REDIS_URL` | 多 worker 生产必配;单机开发可留空(回退内存) |
| `CAPTCHA_ENABLED` / `LOGIN_MAX_FAILURES` / `LOGIN_LOCK_MINUTES` | 认证安全开关 |
| `DEEPSEEK_API_KEY` / `DEEPSEEK_*` | AI 分析(无 Key 回退规则引擎) |
| `SEARCH_API_KEY` | 博查 Web 搜索(无 Key 外部舆情降级) |

> 真实 `*.xlsx`/`*.csv`(对账单、项目统计表)不在仓库,需单独拷贝到项目根目录。

---

## 九、注意事项

- 后端务必在 `backend/` 目录下启动(pydantic 按 cwd 找 `.env`)。
- 依赖装在 `backend/.venv`(不是仓库根的 `.venv`)。
- 上线后:①改掉所有默认账号密码 `123456`;②适时轮换 `DEEPSEEK_API_KEY` / 博查 key / 服务器 root 密码。
- 换会话 / 换机:根目录 `CLAUDE.md` 记录了项目现状与协作约定,运行 `claude` 会自动读取快速接手。

---

## 十、安全增强实施方案(规划):RSA+AES 传输加密 + Docker Compose

> 状态:**规划/待实施**(P2)。本节为具体实现方案,开工前需确认下方「待决策项」。

### ⚠️ 两个前提(决定方案能否真正生效)
1. **RSA+AES 应用层加密不能替代 HTTPS/TLS,只能叠加其上。** 它只加密请求/响应**体**,URL、Header、JWT 仍明文;且公钥要发给前端,**无 TLS 时中间人可在 `/public-key` 响应里掉包公钥**,整套被瓦解。故它属「纵深防御 / 密评应用层加密」,**HTTPS 是地基**(见 `安全加固方案.md` 第一步,生产当前仍 `listen 80`)。
2. **浏览器 `window.crypto.subtle`(Web Crypto)仅在 HTTPS/localhost 可用。** 当前生产为 HTTP,原生加密 API 不可用 → 要么先上 HTTPS(推荐),要么退回纯 JS 库(jsencrypt/crypto-js,强度更弱)。

**建议顺序:先 HTTPS → 再叠加 RSA+AES → 用 Docker Compose 收口部署。**

### 1. RSA + AES 混合传输加密
**信封与流程(每请求一次性 AES 密钥)**:
```
前端: ① 随机 AES-256 密钥 K + 12B IV  ② C=AES-256-GCM(K,IV,明文JSON)
     ③ EK=RSA-OAEP(SHA-256,后端公钥,K)  ④ 发送 {k:EK, iv, d:C} + Header X-Encrypted:1
后端: ⑤ RSA 私钥解出 K → ⑥ AES-GCM 解出明文 → 业务处理 → ⑦ 响应用同一 K+新IV 加密回传
前端: ⑧ 用本地 K 解出响应明文
```
- **算法**:RSA-2048 **OAEP(SHA-256)** + **AES-256-GCM**(带认证 tag,保完整性);一次一密,无长期对称密钥。
- **防重放(等保建议)**:明文体加 `_ts`+`_nonce`,后端校验时间窗(±300s)+ nonce 未用过(存 Redis,复用 `core/store.py`)。
- **后端改动**:`requirements.txt` 加 `cryptography`;`core/config.py` 加 `CRYPTO_ENABLED`/`RSA_PRIVATE_KEY_*`(沿用 `CAPTCHA_ENABLED` 开关范式);新增 `core/crypto.py`(密钥载入/解密信封/加密响应/防重放)、`endpoints/crypto.py`(`GET /crypto/public-key`);`main.py` 挂 `CryptoMiddleware`(入站解密重写 body、出站 JSON 加密,置于 AuditMiddleware 外层)。私钥 PEM 放 `secrets/`(chmod 600、gitignore、属主 www-data),提供 `scripts/gen_rsa.py`,支持轮换。
- **前端改动**:`utils/crypto.js`(优先 Web Crypto,启动拉公钥缓存);`api/request.js` 请求/响应拦截器加解密。
- **豁免透传**(不加密):`multipart` 上传、二进制下载(export/print/legal-doc/attachment/detail)、验证码图片、health、`/crypto/public-key`。按 Content-Type + 路径后缀跳过。
- **HTTP 兜底**(暂不上 HTTPS 时):jsencrypt(RSA)+crypto-js(AES-CBC+HMAC),明确弱于 GCM/OAEP,仅过渡。
- **灰度/验收**:`CRYPTO_ENABLED` 开关;开后 Network 确认请求体为密文信封、响应可解、登录/上传/下载全链路正常;`core/crypto.py` 往返 + 防重放单测。

### 2. Docker Compose 容器化与加固
**架构(仅 nginx 对外)**:`nginx(alpine)` → `backend(uvicorn 2workers,非root)` → `mysql:8.0` + `redis:7`;后三者仅在 `backend_net`(internal),不映射宿主端口。
- **文件**:`backend/Dockerfile`(python:3.13-slim)、`frontend/Dockerfile`(多阶段 node build → nginx:alpine)、`docker-compose.yml`、`deploy/nginx.docker.conf`(TLS+安全响应头/HSTS)、`.env.docker`(gitignore)、`.dockerignore`。
- **加固**:端口收敛(仅 nginx 80/443);`user`/`no-new-privileges`/`cap_drop:[ALL]`/`read_only`+`tmpfs`;密钥用 `env_file`/`secrets` 不进镜像;持久卷 `mysql_data`/`redis_data`/`uploads`/`certs`;健康检查 + `restart: unless-stopped` + `depends_on: service_healthy`;`mem_limit` 资源上限。
- **⚠️ 内存约束**:生产 ECS ~1.6GB(门票台账曾 OOM),全容器化偏紧。三选一:①升配 ≥4GB(推荐);②MySQL 留宿主机只容器化应用;③加 2GB swap + 调小 `innodb_buffer_pool_size`。
- **迁移**:现网 systemd + 宿主 nginx/mysql/redis → 容器需 `mysqldump` 导出导入卷、停 systemd 避端口冲突、先 staging 跑通再切、保留回滚。

### 待决策项(开工前确认)
1. 是否**先上 HTTPS** 再做 RSA+AES(推荐;否则原生加密不可用且公钥分发不可信)。
2. 加密范围:**全部 JSON 接口**(推荐,合密评)/ 仅敏感接口。
3. Docker 的 **MySQL 摆放**:升配全容器化(推荐)/ MySQL 留宿主 / 维持 1.6GB+swap+调优。

### 里程碑
HTTPS(前置)→ RSA+AES(后端 crypto+中间件+公钥接口 → 前端 utils+拦截器 → 开关灰度)→ Docker Compose(staging 跑通 → 内存方案定夺 → 数据迁移 → 切换)→ 回填 `安全加固方案.md` 与本 README 进度。
