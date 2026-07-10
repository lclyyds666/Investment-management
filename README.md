# 山东出版供应链管理公司业务平台

企业级业务平台，采用前后端分离架构。

| 层 | 技术 |
| --- | --- |
| 前端 | Vue 3 + Vite + Element Plus + ECharts |
| 后端 | Python FastAPI + SQLAlchemy 2.0 |
| 数据库 | MySQL 8.0 |

## 项目结构

```
.
├── init.sql      # 数据库建表 + 种子数据脚本（手动导入 MySQL 用）
├── backend/      # FastAPI 后端服务（见 backend/README.md）
└── frontend/     # Vue3 前端应用（见 frontend/README.md）
```

---

# 🚀 零基础本地运行指南（小白专用）

> 目标：在自己的 Windows 电脑上，用 VSCode 把这个平台完整跑起来。
> 请**严格按顺序**一步步来，每一步都做完再做下一步。

整个过程分 4 大步：
**① 装软件 → ② 准备数据库 → ③ 启动后端 → ④ 启动前端**

> 💡 **偷懒提示**：完成了 ①装软件 和 ②准备数据库 之后，第 ③④ 步可以直接
> **双击根目录的 `start.bat`** 一键完成（自动建虚拟环境、装依赖、同时启动前后端并打开浏览器）。
> 如果想了解每一步在做什么，或 `start.bat` 出错了，再按下面 ③④ 手动操作。
> 想停止服务时，**双击 `stop.bat`** 即可一键关闭前后端（无需手动找窗口）。

---

## ① 第一步：安装需要的软件（只需装一次）

按顺序下载安装这 4 个软件，安装时**一路点“下一步/Next”即可**，特别注意下面标⚠️的地方。

| 软件 | 用途 | 下载地址 | 注意事项 |
| --- | --- | --- | --- |
| **Python 3.10+** | 运行后端 | https://www.python.org/downloads/ | ⚠️ 安装第一屏一定要勾选 **“Add Python to PATH”** |
| **Node.js (LTS 版)** | 运行前端 | https://nodejs.org/ | 选左边的 **LTS** 版本，默认安装 |
| **MySQL 8.0** | 数据库 | https://dev.mysql.com/downloads/installer/ | ⚠️ 安装时设置的 **root 密码一定要记住** |
| **VSCode** | 写代码/运行 | https://code.visualstudio.com/ | 默认安装 |

**验证是否装好**：安装完后，按 `Win + R`，输入 `cmd` 回车，打开黑色命令行窗口，分别输入下面两行（每行回车一次），能显示版本号就说明成功：

```bash
python --version      # 显示类似 Python 3.12.x
node --version        # 显示类似 v20.x.x
```

> 如果提示“不是内部或外部命令”，说明上面的软件没装好或没勾 PATH，重装一次。

### 在 VSCode 里装 2 个插件（可选但推荐）
打开 VSCode → 左侧点击四个方块的“扩展”图标 → 搜索并安装：
- **Python**（作者 Microsoft）
- **Vue - Official**（Vue 官方插件）

---

## ② 第二步：用 VSCode 打开项目 + 准备数据库

### 2.1 打开项目
打开 VSCode → 顶部菜单 **文件(File) → 打开文件夹(Open Folder)** → 选择本项目文件夹 `D:\1` → 打开。

左侧就能看到 `backend`、`frontend`、`init.sql` 等内容。

### 2.2 创建数据库并导入数据
我们要把 `init.sql` 导入 MySQL（它会自动建库、建表、并写入演示数据）。任选一种方式：

**方式 A（推荐，命令行最简单）**：在 VSCode 顶部菜单点 **终端(Terminal) → 新建终端(New Terminal)**，在下方出现的终端里输入：

```bash
mysql -u root -p < init.sql
```

回车后会提示 `Enter password:`，输入你安装 MySQL 时设置的 **root 密码**（输入时不显示是正常的），再回车。看到 `数据库初始化完成` 字样就成功了。

> ⚠️ 如果提示 `mysql 不是内部或外部命令`，是因为 MySQL 没加入 PATH。可改用方式 B。

**方式 B（图形化工具）**：下载安装 **Navicat** 或免费的 **DBeaver** / **MySQL Workbench**，连接到本地 MySQL（主机 `localhost`、用户 `root`、密码为你设置的密码），打开 `init.sql` 文件，点“运行/执行”。

成功后，数据库里会有 `sd_publish_scm` 库，包含 4 张表和演示数据。

---

## ③ 第三步：启动后端（FastAPI）

在 VSCode 终端里依次执行下面命令。**第一次运行要做 1~4 步，以后每次只需第 4 步。**

```bash
# 1. 进入后端目录
cd backend

# 2. 创建虚拟环境（独立的 Python 运行环境，只需做一次）
python -m venv .venv

# 3. 激活虚拟环境（每次新开终端都要执行）
.venv\Scripts\activate
#   成功后，命令行最前面会出现 (.venv) 字样

# 4. 安装依赖（只需做一次，约 1~2 分钟）
pip install -r requirements.txt
```

接着配置数据库密码：
- 在左侧文件树里找到 `backend` 文件夹，把里面的 **`.env.example`** 复制一份，改名为 **`.env`**
  （可以右键 `.env.example` → 复制，再右键 → 粘贴，然后重命名为 `.env`）
- 双击打开 `.env`，把 `DB_PASSWORD=your_password` 改成你的 MySQL root 密码，保存。

最后**启动后端服务**：

```bash
uvicorn app.main:app --reload
```

看到 `Uvicorn running on http://127.0.0.1:8000` 就成功了。

✅ **验证**：浏览器打开 http://127.0.0.1:8000/docs ，能看到接口文档页面即正常。

> ⚠️ 这个终端窗口要**一直开着别关**，关了后端就停了。

---

## ④ 第四步：启动前端（Vue）

**再开一个新终端**（终端 → 新建终端，不要关掉后端那个），执行：

```bash
# 1. 进入前端目录
cd frontend

# 2. 安装依赖（只需做一次，约 2~3 分钟）
npm install

# 3. 启动前端
npm run dev
```

看到 `Local: http://localhost:5173/` 就成功了。

✅ **打开浏览器访问 http://localhost:5173** ，就能看到登录页面！

---

## 🎉 登录体验

用下面任意账号登录（**密码都是 `123456`**），不同角色能看到不同的菜单和权限：

| 账号 | 角色 | 能做什么 |
| --- | --- | --- |
| `leader` | 领导班子 | 看经营数据看板、审批合同 |
| `staff` | 业务骨干 | 看经营数据看板、录入/提交合同 |
| `user` | 普通用户 | 仅查看已通过的合同 |
| `admin` | 超级管理员 | 全部权限 |

---

## ❓ 常见问题

- **以后再次运行怎么办？**
  不用重装。开两个终端：
  1. 后端：`cd backend` → `.venv\Scripts\activate` → `uvicorn app.main:app --reload`
  2. 前端：`cd frontend` → `npm run dev`

- **登录提示“账号或密码错误”？**
  确认第二步的 `init.sql` 已成功导入；密码是 `123456`。

- **页面能打开但数据加载失败 / 一直转圈？**
  多半是后端没启动，或 `.env` 里数据库密码填错。检查后端终端有没有报错。

- **`.venv\Scripts\activate` 报“无法加载脚本，因为禁止运行脚本”？**
  以管理员身份打开 PowerShell，执行一次：
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`，输入 `Y` 回车，再重试。

- **端口被占用（8000 或 5173）？**
  关掉占用的程序，或改用其他端口启动（后端加 `--port 8001`）。

---

# 📊 经营数据来源说明（重要）

- **经营看板 / 首页大屏 / AI 诊断** 的营收、成本、利润、订单数，均来自独立表 `biz_operation_data`，
  由 `python -m app.db.init_db`（或 `init.sql`）写入的**演示种子数据**，并可通过「领导录入经营数据」接口手工新增。
- **合同（`biz_contract`）与经营数据当前相互独立**：合同金额不会自动汇入经营看板。
- 若需要“经营数据由合同/订单真实汇总”，属于业务口径调整，需要单独开发汇总逻辑（可另行提出）。

---

# 🚀 生产部署（Ubuntu 22.04 · 公网 IP `39.107.52.146` 直连，无域名）

架构：`浏览器 → Nginx:80（静态前端 + 反向代理 /api） → 后端 Uvicorn:127.0.0.1:8000 → MySQL`
（前端同源访问 `/api`，无需 CORS。）

部署产物：`deploy/nginx.conf`、`deploy/sd-scm-backend.service`、`frontend/.env.production`。

## ① 本地打包前端并上传代码
```bash
# 本地（Windows）先构建前端，生成 frontend/dist
cd frontend && npm install && npm run build

# 上传整个项目到服务器 /opt/sd-scm（Windows 可用 WinSCP；或 scp/rsync）
scp -r ./*  root@39.107.52.146:/opt/sd-scm/
```

## ② 服务器：数据库
```bash
apt update && apt install -y mysql-server
mysql -u root -p < /opt/sd-scm/init.sql          # 建库建表
cd /opt/sd-scm/backend                            # 下一步的 init_db 会补签名等种子
```

## ③ 服务器：后端（虚拟环境需在服务器重建）
```bash
apt install -y python3-venv python3-pip
cd /opt/sd-scm/backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # 若无则手建；务必修改下面三项：
#   DB_PASSWORD=<你的MySQL密码>
#   SECRET_KEY=<改成随机长字符串:  openssl rand -hex 32>
#   DEBUG=false
python -m app.db.init_db                          # 写入 7 角色账号 + 签名等种子

# 安装 systemd 守护
cp /opt/sd-scm/deploy/sd-scm-backend.service /etc/systemd/system/
chown -R www-data:www-data /opt/sd-scm
systemctl daemon-reload
systemctl enable --now sd-scm-backend
systemctl status sd-scm-backend                   # 或 journalctl -u sd-scm-backend -f
```

## ④ 服务器：安装并启动 Nginx
```bash
apt install -y nginx
cp /opt/sd-scm/deploy/nginx.conf /etc/nginx/conf.d/sd-scm.conf
rm -f /etc/nginx/sites-enabled/default             # 去掉默认站点，避免冲突
nginx -t && systemctl restart nginx
```

## ⑤ 放行 80 端口
```bash
ufw allow 80/tcp    # 若启用了 ufw
```
并在**云厂商安全组**放行 TCP 80。随后浏览器访问 **http://39.107.52.146** 即可。

> 更新代码：本地 `npm run build` 后重传 `frontend/dist`；后端改动重传后 `systemctl restart sd-scm-backend`。

---

# ✅ 正式投产前检查清单（当前为可试运行的 MVP）

| 项 | 现状 | 投产前建议 |
| --- | --- | --- |
| `SECRET_KEY` | 默认 `change-me...` | **必须**改为随机串 |
| `DEBUG` | `true` | 生产设为 `false` |
| 账号密码 | 全部 `123456` | 上线后立即改密 |
| 传输加密 | 纯 HTTP（IP 直连） | 内网可用；公网长期用建议加 HTTPS |
| 渠道账号密码 | 明文存储（演示用） | 敏感信息应加密或改用密钥托管 |
| 演示数据 | 经营/订单/公告/AI/签名为 Mock | 按真实业务替换 |
| 数据备份 | 无 | 配置 MySQL 定时备份 |

---

# 🖥️ 换电脑继续开发 & 上传 GitHub

## 一、先了解:哪些东西**不在** Git 里(需单独处理)

出于安全,以下文件**已被 `.gitignore` 排除,不会上传 GitHub**,换电脑时要单独准备:

| 文件 | 说明 | 换机怎么办 |
| --- | --- | --- |
| `backend/.env` | 含数据库密码、`DEEPSEEK_API_KEY` 等**密钥** | 新机器上照 `backend/.env.example` 重建,填入自己的密钥 |
| `*.xlsx` / `*.csv` | 对账单、项目统计表等**真实财务数据** | 用 U 盘 / 私有网盘单独拷贝到项目根目录 |
| `.venv/`、`node_modules/` | 依赖,体积大 | 新机器上重新安装(见下) |
| `*.log` | 运行日志 | 无需迁移 |

> ⚠️ **强烈建议把 GitHub 仓库设为「私有(Private)」**——本项目含企业业务逻辑,即使已排除数据文件也不宜公开。

## 二、把项目上传到 GitHub(在当前这台电脑操作)

本仓库**已关联远程** `origin` → `https://github.com/lclyyds666/Investment-management.git`,
所以日常上传只需三步(在**项目根目录**执行):

```bash
git add .
git commit -m "说明本次改动"
git push
```

- `.env` 与 `*.xlsx` 已被 `.gitignore` 自动排除,不会上传。
- **登录认证**:若弹出登录/输入密码,GitHub 已不支持账号密码,请粘贴 **Personal Access Token**
  (GitHub → Settings → Developer settings → Personal access tokens 生成),或装 [GitHub CLI](https://cli.github.com/) 后 `gh auth login` 一次。
- 想换成自己的新仓库:`git remote set-url origin https://github.com/<用户名>/<仓库名>.git` 后再 `git push -u origin main`。
- ⚠️ 建议在 GitHub 仓库 **Settings → 改为 Private(私有)**,避免企业业务代码公开。

## 三、在**另一台电脑**上继续开发

1. 按本文档「① 安装软件」装好 **Git、Python 3.10+、Node.js LTS、MySQL 8.0**。
2. 克隆并进入项目:
   ```bash
   git clone https://github.com/<你的用户名>/<仓库名>.git
   cd <仓库名>
   ```
3. **拷回被忽略的文件**:把 `backend/.env`(或照 `.env.example` 新建并填密钥)和需要的 `*.xlsx` 数据文件放回对应位置。
4. **数据库**:`mysql -u root -p < init.sql`,再 `cd backend` 后 `python -m app.db.init_db`。
   最后依次执行 `backend/migrations/` 下的迁移脚本(把商用改造的表结构补齐):
   ```bash
   mysql -u root -p sd_publish_scm < backend/migrations/20260710_commercial_data_link.sql
   mysql -u root -p sd_publish_scm < backend/migrations/20260710_financial_metrics.sql
   mysql -u root -p sd_publish_scm < backend/migrations/20260710_project_metrics.sql
   ```
5. **后端**:`cd backend` → `python -m venv .venv` → 激活 → `pip install -r requirements.txt` → `uvicorn app.main:app --reload`(**务必在 `backend/` 目录下启动**,否则读不到 `.env`)。
6. **前端**:`cd frontend` → `npm install` → `npm run dev`。

## 四、关于「继续我们的 Claude 对话」

Claude Code 的**对话记录保存在本机**(`~/.claude/` 目录下,按项目路径归档),**不随 Git 仓库转移**——所以在新电脑上是一个全新的 Claude 会话,看不到这台电脑上的历史聊天。两个办法:

- **推荐**:仓库里已有一份 **`CLAUDE.md`**(项目现状、已完成的商用改造、注意事项)。在新电脑的项目目录运行 `claude`,它会自动读取 `CLAUDE.md` 快速接手,无需你复述背景。
- **在同一台电脑**恢复本次对话:在项目目录运行 `claude --resume`(弹出会话列表选择),或 `claude -c` 继续最近一次对话。
- (进阶,不保证成功)对话原始记录在 `~/.claude/projects/` 下,理论上可整目录拷到新机器,但因目录名按路径哈希、版本差异等原因**可能无法直接识别**,一般不建议依赖此法。
