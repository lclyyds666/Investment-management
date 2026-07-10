@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ================================================
echo   山东出版供应链管理公司业务平台  一键启动
echo ================================================
echo.

REM ---------- 环境检查 ----------
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10+ 并勾选 "Add to PATH"。
    pause
    exit /b 1
)
where node >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到 Node.js，请先安装 Node.js LTS 版本。
    pause
    exit /b 1
)

REM ============================================================
REM  后端：虚拟环境 + 依赖 + .env
REM ============================================================
cd /d "%~dp0backend"

if not exist ".venv\Scripts\activate.bat" (
    echo [后端] 首次运行：创建虚拟环境...
    python -m venv .venv
    echo [后端] 安装依赖（首次较慢，请耐心等待 1-2 分钟）...
    call ".venv\Scripts\activate.bat"
    python -m pip install --upgrade pip >nul
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 后端依赖安装失败，请检查网络后重试。
        pause
        exit /b 1
    )
)

if not exist ".env" (
    echo [后端] 未发现 .env，已从 .env.example 自动复制一份。
    echo        ^>^>^> 请记得打开 backend\.env 修改数据库密码 DB_PASSWORD ^<^<^<
    copy ".env.example" ".env" >nul
)

REM 在独立窗口启动后端服务
echo [后端] 正在新窗口启动 FastAPI (http://127.0.0.1:8000) ...
start "后端 FastAPI :8000" cmd /k "cd /d "%~dp0backend" && call .venv\Scripts\activate.bat && uvicorn app.main:app --reload"

REM ============================================================
REM  前端：依赖 + 启动
REM ============================================================
cd /d "%~dp0frontend"

if not exist "node_modules" (
    echo [前端] 首次运行：安装依赖（首次较慢，请耐心等待 2-3 分钟）...
    call npm install
    if errorlevel 1 (
        echo [错误] 前端依赖安装失败，请检查网络后重试。
        pause
        exit /b 1
    )
)

echo [前端] 正在新窗口启动 Vue (http://localhost:5173) ...
start "前端 Vue :5173" cmd /k "cd /d "%~dp0frontend" && npm run dev"

REM ---------- 等待前端就绪后打开浏览器 ----------
echo.
echo 启动中，约 10 秒后将自动打开浏览器...
timeout /t 10 /nobreak >nul
start "" http://localhost:5173

echo.
echo ================================================
echo  已在两个独立窗口分别启动【后端】和【前端】。
echo  - 关闭对应窗口即可停止该服务。
echo  - 浏览器访问: http://localhost:5173
echo  - 演示账号: leader / staff / user  密码: 123456
echo.
echo  提示: 首次使用请先把 init.sql 导入 MySQL（见 README）。
echo ================================================
echo.
echo 本窗口可以关闭。
pause
endlocal
