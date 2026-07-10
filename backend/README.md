# 山东出版供应链管理公司业务平台 — 后端

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
