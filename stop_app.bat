@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

set "PROJECT_ROOT=%~dp0"
if "%PROJECT_ROOT:~-1%"=="\" set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"
set "PID_DIR=%PROJECT_ROOT%\.pids"
set "BACKEND_PID_FILE=%PID_DIR%\backend.pid"
set "FRONTEND_PID_FILE=%PID_DIR%\frontend.pid"

echo ======================================
echo   Backtrader Web - 停止项目
echo ======================================
echo.

call :stop_from_pidfile "%BACKEND_PID_FILE%" "后端"
call :stop_from_pidfile "%FRONTEND_PID_FILE%" "前端"

call :kill_port 8000 "后端"
call :kill_port 3000 "前端"

echo.
echo [OK] 停止流程完成
echo.
exit /b 0

:stop_from_pidfile
set "PID_FILE=%~1"
set "SERVICE_NAME=%~2"
if not exist "%PID_FILE%" (
    echo [INFO] %SERVICE_NAME% PID 文件不存在
    exit /b 0
)
set "PID_VALUE="
for /f "usebackq delims=" %%i in ("%PID_FILE%") do set "PID_VALUE=%%i"
if not defined PID_VALUE (
    del /f /q "%PID_FILE%" >nul 2>nul
    echo [INFO] %SERVICE_NAME% PID 文件为空，已清理
    exit /b 0
)
tasklist /FI "PID eq %PID_VALUE%" | findstr /R /C:" %PID_VALUE% " >nul
if errorlevel 1 (
    echo [INFO] %SERVICE_NAME% 进程未运行，PID: %PID_VALUE%
    del /f /q "%PID_FILE%" >nul 2>nul
    exit /b 0
)
echo [INFO] 正在停止 %SERVICE_NAME%，PID: %PID_VALUE%
taskkill /PID %PID_VALUE% /T /F >nul 2>nul
if errorlevel 1 (
    echo [WARN] 无法通过 PID 文件停止 %SERVICE_NAME%，PID: %PID_VALUE%
) else (
    echo [OK] %SERVICE_NAME% 已停止
)
del /f /q "%PID_FILE%" >nul 2>nul
exit /b 0

:kill_port
set "TARGET_PORT=%~1"
set "SERVICE_NAME=%~2"
set "FOUND_PORT_PID="
for /f "tokens=5" %%i in ('netstat -ano ^| findstr /R /C:":%TARGET_PORT% .*LISTENING"') do (
    set "FOUND_PORT_PID=%%i"
    goto :kill_port_found
)
goto :kill_port_done
:kill_port_found
echo [INFO] 释放 %SERVICE_NAME% 端口 %TARGET_PORT%，PID: !FOUND_PORT_PID!
taskkill /PID !FOUND_PORT_PID! /T /F >nul 2>nul
:kill_port_done
exit /b 0
