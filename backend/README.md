# 山东出版供应链管理有限公司业务平台 — 后端

基于 **FastAPI + SQLAlchemy 2.0 + MySQL** 的业务平台后端服务。

## 技术栈

- Python 3.10+
- FastAPI
- SQLAlchemy 2.0（ORM）
- MySQL 8.0（PyMySQL 驱动）
- Pydantic v2 / pydantic-settings（配置与校验）
- Alembic（数据库迁移）

## 目录结构

```
backend/
├── app/
│   ├── main.py              # 应用入口
│   ├── core/
│   │   └── config.py        # 全局配置（读取 .env）
│   ├── db/
│   │   ├── base.py          # ORM 基类
│   │   └── session.py       # 引擎与会话
│   ├── models/              # ORM 模型
│   ├── schemas/             # Pydantic 模型
│   └── api/
│       └── v1/
│           ├── router.py    # v1 路由汇总
│           └── endpoints/   # 各业务端点
├── requirements.txt
└── .env.example
```

## 快速开始

```bash
# 1. 创建并激活虚拟环境
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux / macOS

# 2. 安装依赖
pip install -r requirements.txt

# 3. 准备环境变量
copy .env.example .env        # Windows
# cp .env.example .env        # Linux / macOS
# 然后修改 .env 中的数据库连接信息

# 4. 在 MySQL 中创建数据库
#   CREATE DATABASE sd_publish_scm DEFAULT CHARACTER SET utf8mb4;

# 5. 初始化数据库（建表 + 写入种子数据）
python -m app.db.init_db

# 6. 启动开发服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

启动后访问：

- 接口文档（Swagger）：http://localhost:8000/docs
- 健康检查：http://localhost:8000/api/v1/health

## 角色与权限（RBAC）

| 角色 | 标识 | 主要权限 |
| --- | --- | --- |
| 普通用户 | `normal` | 仅查看已通过的合同 |
| 业务骨干 | `staff` | 录入/修改/提交合同、查看经营数据看板 |
| 领导班子 | `leader` | 审批合同、查看全量经营数据、录入经营数据 |

- 鉴权方式：登录 `POST /api/v1/auth/login`（OAuth2 表单）获取 JWT，
  后续请求在 `Authorization: Bearer <token>` 头携带。
- 权限控制：`app/api/deps.py` 中的 `require_roles(...)` 依赖按角色拦截；
  `is_superuser` 账号始终放行。

**默认账号（密码均为 `123456`，生产请立即修改）：**
`admin`（超管/领导）、`leader`（领导班子）、`staff`（业务骨干）、`user`（普通用户）

## 主要接口

| 模块 | 方法 路径 | 说明 | 角色 |
| --- | --- | --- | --- |
| 认证 | POST `/auth/login` | 登录获取令牌 | 公开 |
| 认证 | GET `/auth/me` | 当前用户 | 登录 |
| 合同 | GET `/contracts` | 合同列表（按角色过滤） | 登录 |
| 合同 | POST `/contracts` | 新建合同 | staff |
| 合同 | POST `/contracts/{id}/submit` | 提交审批 | staff |
| 合同 | POST `/contracts/{id}/approve` | 审批(通过/驳回) | leader |
| 经营 | GET `/operation/dashboard` | 看板聚合数据 | staff/leader |

## Unified Organization Permission Migration

Run the following production sequence from the `backend` directory. Review
`migration-preview.json` before applying the migration.

```powershell
mysql -u USER -p DATABASE < migrations/20260813_unified_organization_permissions.sql
python -m app.db.init_db
python scripts/migrate_company_roles_to_assignments.py --report migration-preview.json
python scripts/migrate_company_roles_to_assignments.py --apply --report migration-applied.json
python -m unittest tests.test_assignment_permissions tests.test_company_permissions tests.test_portal_api -v
```

The migration command exits with code `2` when its report contains unresolved
rows that require operator review. Resolve those rows, rerun the preview, and
then apply only after the report is acceptable.

The legacy role tables and their rows remain untouched by this process. The
rollback boundary is the new permission feature routing: disable that routing
and continue reading the untouched legacy role rows while the migration is
investigated or reversed operationally.

## Active Legacy Workflow Cutover

Do not enable version 2 submissions until this sequence finishes successfully:

1. Pause all new contract and approval-form submissions.
2. Run `python -m scripts.migrate_active_workflows --report active-workflow-preview.json`.
3. Resolve every `needs_designation` and `invalid_state` row in the report. A
   designated position must have exactly one eligible person; the migration never
   chooses between zero or multiple candidates.
4. Rerun the dry-run until it contains no unresolved pending row, then run
   `python -m scripts.migrate_active_workflows --apply --report active-workflow-applied.json`.
5. Verify the database contains no `pending` contract or approval form whose
   `workflow_instance_id` is null, and compare the applied report to the preview.
6. Enable version 2 submissions.

The dry-run performs no writes. Apply materializes only pending legacy rows whose
current step maps to a shared position and whose future designated positions each
have exactly one eligible person. Existing approved/rejected rows remain version 1
history and receive no workflow instance or runtime task. Migration also creates no
synthetic `SUBMIT`, workflow action, `Approval`, or `ApprovalFormAction` audit row;
the existing version 1 history remains authoritative for actions before cutover.
The report is written and flushed to a same-directory temporary file before the
database commit, then atomically renamed after commit. If that final rename fails,
the command exits nonzero and prints the retained temporary path for recovery; do
not rerun apply until that report has been preserved and the database verified.
