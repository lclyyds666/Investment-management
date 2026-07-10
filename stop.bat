@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ================================================
echo   山东出版供应链管理公司业务平台  一键停止
echo ================================================
echo.
echo 正在查找并停止 后端(8000) 与 前端(5173) 服务...
echo.

REM 依次处理两个端口
for %%P in (8000 5173) do (
    set "FOUND=0"
    REM 找出监听该端口的进程 PID（netstat 第 5 列）
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%%P " ^| findstr LISTENING') do (
        echo 端口 %%P  ->  结束进程 PID %%a
        taskkill /PID %%a /F >nul 2>nul
        set "FOUND=1"
    )
    if "!FOUND!"=="0" echo 端口 %%P  ->  未发现运行中的服务。
)

echo.
echo 完成。前后端服务已停止（对应的命令行窗口也会自动关闭）。
echo.
pause
endlocal
