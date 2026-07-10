# 山东出版供应链管理公司业务平台 — 前端

基于 **Vue 3 + Vite + Element Plus** 的业务平台前端。

## 技术栈

- Vue 3（`<script setup>`）
- Vite 6
- Element Plus（按需自动导入）
- Vue Router 4
- Pinia（状态管理）
- Axios（HTTP 请求）

## 目录结构

```
frontend/
├── index.html
├── vite.config.js          # 含 /api 代理到后端
├── .env.development        # 开发环境变量
├── .env.production         # 生产环境变量
└── src/
    ├── main.js             # 应用入口
    ├── App.vue
    ├── api/                # 接口封装
    │   ├── request.js      # axios 实例与拦截器(含 401 跳登录)
    │   ├── auth.js         # 登录 / 当前用户
    │   ├── contract.js     # 合同 / 审批
    │   └── operation.js    # 经营数据
    ├── components/
    │   └── BaseChart.vue   # ECharts 通用封装(自适应)
    ├── router/             # 路由(含角色 meta)
    ├── permission.js       # 全局路由守卫(登录 + 角色拦截)
    ├── store/              # Pinia 状态(user：token/role)
    ├── layout/             # 主框架布局(按角色动态菜单)
    ├── styles/             # 全局样式
    └── views/              # 页面
        ├── login/          # 登录页
        ├── dashboard/      # 首页
        ├── operation/      # 经营数据可视化(ECharts)
        ├── contract/       # 合同管理
        ├── approval/       # 审批中心(领导班子)
        └── error/
```

## 权限与路由拦截

- 登录状态与角色存于 Pinia(`store/user.js`)并持久化到 `localStorage`。
- `permission.js` 全局守卫：未登录跳转 `/login`；路由 `meta.roles` 控制页面级权限；
  侧边栏菜单按当前角色动态过滤。
- 角色：`normal` 普通用户 / `staff` 业务骨干 / `leader` 领导班子。

**演示账号（密码均 `123456`）：** `leader` / `staff` / `user`

## 快速开始

```bash
# 1. 安装依赖（推荐 Node.js 18+）
npm install

# 2. 启动开发服务
npm run dev

# 3. 构建生产包
npm run build
```

开发服务默认运行在 http://localhost:5173 ，
并通过 Vite 代理将 `/api` 请求转发到后端 `http://127.0.0.1:8000`。
