# 山东出版供应链管理公司业务平台

企业级业务中台,前后端分离。覆盖 **合同全生命周期审批、经营数据看板、数据大屏、渠道集成、智慧财务、客户 AI 尽调、用户与权限** 等模块。

| 层 | 技术 |
| --- | --- |
| 前端 | Vue 3 + Vite + Element Plus + ECharts |
| 后端 | Python FastAPI + SQLAlchemy 2.0 |
| 数据库 | MySQL 8.0(库名 `sd_publish_scm`) |
| 缓存 | Redis(可选;缺失自动回退进程内存) |
| AI | DeepSeek(OpenAI 兼容协议)+ 博查 Web 搜索 |

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
| **合同全生命周期** | 新建(申请部门/编号/名称/类型/是否内部/标的/签订日期/客户/金额/币种/付款条件/**附件真实上传**);5 节点审批流;**合同台账导出 CSV**;**「法律文件审批表」打印** |
| **审批中心** | 待我审批列表;逐级通过(附电子签章)/驳回(原因必填);审批意见留痕 |
| **客户档案库** | 增删改查 + 手机号脱敏;**AI 尽职调查**(PDF/Word/Excel **批量上传** → 解析 → 融合博查外部资讯 → DeepSeek 生成分析报告,两级降级不 500) |
| **经营数据 & 大屏** | 项目维度经营看板;数据大屏(KPI/趋势/**数据驱动地图飞线**/省份联动/审批跑马灯/AI 雷达) |
| **渠道业务管理** | 渠道 CRUD;CSV 导入/回传;列映射汇入经营表,联动看板/大屏 |
| **智慧财务管理** | 菜单组:资金管理(建设中)+ 发票管理;对账单 xlsx 解析 → 财务指标聚合 |

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

**合同审批链**(顺序即流转顺序):

```
业务经办 → 供管公司负责人 → 法律顾问 → 投资公司法务风控 → 投资公司分管领导
```

除「业务经办」(提交时自动完成第 0 级并附签)外,其余节点在审批中心均需/可填写审批意见,并自动附加电子签章;末级通过即合同 `approved`。

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
```

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
