@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

set "PROJECT_ROOT=%~dp0"
if "%PROJECT_ROOT:~-1%"=="\" set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"
set "BACKEND_DIR=%PROJECT_ROOT%\src\backend"
set "FRONTEND_DIR=%PROJECT_ROOT%\src\frontend"
set "PID_DIR=%PROJECT_ROOT%\.pids"
set "LOG_DIR=%PROJECT_ROOT%\logs"
set "BACKEND_PID_FILE=%PID_DIR%\backend.pid"
set "FRONTEND_PID_FILE=%PID_DIR%\frontend.pid"
set "BACKEND_OUT_LOG=%LOG_DIR%\backend.out.log"
set "BACKEND_ERR_LOG=%LOG_DIR%\backend.err.log"
set "FRONTEND_OUT_LOG=%LOG_DIR%\frontend.out.log"
set "FRONTEND_ERR_LOG=%LOG_DIR%\frontend.err.log"

if not exist "%PID_DIR%" mkdir "%PID_DIR%"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

if /I "%~1"=="__run__" goto :run
if /I "%~1"=="__sync__" goto :run

set "RUN_TOKEN=%RANDOM%_%RANDOM%"
set "ASYNC_LOG=%LOG_DIR%\start_app.%RUN_TOKEN%.async.log"
type nul > "%ASYNC_LOG%"

echo ======================================
echo   Backtrader Web - 后台启动中
echo ======================================
echo.
echo [INFO] 已提交到后台执行
echo [INFO] 实时输出窗口将单独打开，当前终端可继续使用
echo [INFO] 日志文件: %ASYNC_LOG%

powershell -NoProfile -ExecutionPolicy Bypass -Command "$log = [System.IO.Path]::GetFullPath('%ASYNC_LOG%'); $script = [System.IO.Path]::GetFullPath('%~f0'); $runner = '[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [Console]::OutputEncoding; $utf8 = New-Object System.Text.UTF8Encoding($false); [System.IO.File]::WriteAllText(''' + $log + ''', '''', $utf8); & ''' + $script + ''' __sync__ 2>&1 | ForEach-Object { $line = $_.ToString(); [System.IO.File]::AppendAllText(''' + $log + ''', $line + [Environment]::NewLine, $utf8); Write-Output $line }; Write-Host ''''; Write-Host ''[INFO] 启动脚本已执行完成，可关闭此窗口'''; Start-Process -WindowStyle Normal -FilePath 'powershell.exe' -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-NoExit','-Command',$runner | Out-Null"

endlocal
exit /b 0

:run

echo ======================================
echo   Backtrader Web - 启动项目
echo ======================================
echo.

call :resolve_python
if errorlevel 1 exit /b 1

where node >nul 2>nul
if errorlevel 1 (
    echo [ERROR] 未找到 Node.js，请先安装 Node.js 20+
    exit /b 1
)
for /f "delims=" %%i in ('node --version') do set "NODE_VERSION=%%i"
echo [INFO] Node.js 版本: %NODE_VERSION%

where npm >nul 2>nul
if errorlevel 1 (
    echo [ERROR] 未找到 npm
    exit /b 1
)

call :cleanup_stale_pid "%BACKEND_PID_FILE%"
call :cleanup_stale_pid "%FRONTEND_PID_FILE%"

call :ensure_port_free 8000 "后端"
if errorlevel 1 exit /b 1
call :ensure_port_free 3000 "前端"
if errorlevel 1 exit /b 1

echo [1/5] 检查后端依赖...
pushd "%BACKEND_DIR%" >nul
for %%p in (fastapi uvicorn sqlalchemy pydantic email_validator slowapi jose passlib loguru yaml aiosqlite) do (
    "%PYTHON_EXE%" -c "import %%p" >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] 缺少 Python 依赖: %%p
        echo [HINT] 请执行: "%PYTHON_EXE%" -m pip install -r requirements.txt
        popd >nul
        exit /b 1
    )
)
if "%NEEDS_MT5%"=="1" (
    "%PYTHON_EXE%" -c "import pymt5" >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] 当前 Python 缺少 MT5 依赖: pymt5
        echo [HINT] 请切换到已安装 pymt5 的解释器，或为 "%PYTHON_EXE%" 安装 pymt5
        popd >nul
        exit /b 1
    )
)
if not exist ".env" (
    > ".env" (
        echo DEBUG=true
        echo SECRET_KEY=dev-secret-key-please-change-1234567890
        echo JWT_SECRET_KEY=dev-jwt-secret-key-please-change-1234567890
        echo DATABASE_TYPE=sqlite
        echo DATABASE_URL=sqlite+aiosqlite:///./backtrader.db
        echo CORS_ORIGINS=http://localhost:3000
        echo ADMIN_USERNAME=admin
        echo ADMIN_PASSWORD=admin123
        echo ADMIN_EMAIL=admin@example.com
    )
    echo [INFO] 已创建默认后端 .env
)
popd >nul

echo [2/5] 检查前端依赖...
if not exist "%FRONTEND_DIR%\node_modules" (
    echo [ERROR] 前端依赖未安装
    echo [HINT] 请执行: npm install
    exit /b 1
)

echo [3/5] 启动后端服务...
pushd "%BACKEND_DIR%" >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Start-Process -FilePath '%PYTHON_EXE%' -ArgumentList '-m','uvicorn','app.main:app','--host','0.0.0.0','--port','8000' -WorkingDirectory '%BACKEND_DIR%' -RedirectStandardOutput '%BACKEND_OUT_LOG%' -RedirectStandardError '%BACKEND_ERR_LOG%' -WindowStyle Hidden -PassThru; [System.IO.File]::WriteAllText('%BACKEND_PID_FILE%', [string]$p.Id, [System.Text.Encoding]::ASCII)"
if errorlevel 1 (
    popd >nul
    echo [ERROR] 后端启动失败
    exit /b 1
)
popd >nul
call :wait_for_port 8000 20
if errorlevel 1 (
    echo [ERROR] 后端未在 8000 端口成功启动，请查看日志: %BACKEND_ERR_LOG%
    exit /b 1
)
for /f "usebackq delims=" %%i in ("%BACKEND_PID_FILE%") do set "BACKEND_PID=%%i"
echo [OK] 后端服务启动成功 - PID: %BACKEND_PID%

echo [4/5] 启动前端服务...
pushd "%FRONTEND_DIR%" >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Start-Process -FilePath 'npm.cmd' -ArgumentList 'run','dev' -WorkingDirectory '%FRONTEND_DIR%' -RedirectStandardOutput '%FRONTEND_OUT_LOG%' -RedirectStandardError '%FRONTEND_ERR_LOG%' -WindowStyle Hidden -PassThru; [System.IO.File]::WriteAllText('%FRONTEND_PID_FILE%', [string]$p.Id, [System.Text.Encoding]::ASCII)"
if errorlevel 1 (
    popd >nul
    echo [ERROR] 前端启动失败
    exit /b 1
)
popd >nul
call :wait_for_port 3000 30
if errorlevel 1 (
    echo [WARN] 前端未在 3000 端口确认启动，请查看日志: %FRONTEND_ERR_LOG%
) else (
    for /f "usebackq delims=" %%i in ("%FRONTEND_PID_FILE%") do set "FRONTEND_PID=%%i"
    echo [OK] 前端服务启动成功 - PID: !FRONTEND_PID!
)

echo [5/5] Status
echo   Frontend : http://localhost:3000
echo   Backend  : http://localhost:8000
echo   API Docs : http://localhost:8000/docs
echo   Logs     : %LOG_DIR%
echo   PIDs     : %PID_DIR%
echo.
exit /b 0

:resolve_python
set "PYTHON_EXE="
call :mt5_enabled
if not defined PYTHON_EXE if exist "C:\anaconda3\python.exe" (
    call :python_supports_ctp "C:\anaconda3\python.exe"
    if not errorlevel 1 (
        if "%NEEDS_MT5%"=="1" (
            call :python_supports_mt5 "C:\anaconda3\python.exe"
            if not errorlevel 1 (
                set "PYTHON_EXE=C:\anaconda3\python.exe"
            )
        ) else (
            set "PYTHON_EXE=C:\anaconda3\python.exe"
        )
    )
)
if not defined PYTHON_EXE (
    for %%P in (python.exe) do set "PYTHON_EXE=%%~$PATH:P"
)
if not defined PYTHON_EXE (
    echo [ERROR] 未找到系统 Python，请先安装或激活 Conda / 系统环境
    exit /b 1
)
for /f "delims=" %%i in ('"%PYTHON_EXE%" --version') do set "PYTHON_VERSION=%%i"
echo [INFO] Python 版本: %PYTHON_VERSION%
echo [INFO] Python 解释器: %PYTHON_EXE%
exit /b 0

:mt5_enabled
set "NEEDS_MT5=0"
if exist "%PROJECT_ROOT%\data\manual_gateways.json" (
    findstr /I /C:"\"exchange_type\": \"MT5\"" "%PROJECT_ROOT%\data\manual_gateways.json" >nul 2>nul
    if not errorlevel 1 set "NEEDS_MT5=1"
)
if "%NEEDS_MT5%"=="0" if exist "%BACKEND_DIR%\.env" (
    findstr /R /C:"^MT5_LOGIN=." "%BACKEND_DIR%\.env" >nul 2>nul
    if not errorlevel 1 (
        findstr /R /C:"^MT5_PASSWORD=." "%BACKEND_DIR%\.env" >nul 2>nul
        if not errorlevel 1 set "NEEDS_MT5=1"
    )
)
exit /b 0

:python_supports_ctp
set "CANDIDATE_PY=%~1"
if not defined CANDIDATE_PY exit /b 1
"%CANDIDATE_PY%" -c "import sys; sys.path.insert(0, r'%PROJECT_ROOT%\..\bt_api_py'); from bt_api_py.ctp.client import MdClient; print('ok')" >nul 2>nul
if errorlevel 1 exit /b 1
exit /b 0

:python_supports_mt5
set "CANDIDATE_PY=%~1"
if not defined CANDIDATE_PY exit /b 1
"%CANDIDATE_PY%" -c "import pymt5; print('ok')" >nul 2>nul
if errorlevel 1 exit /b 1
exit /b 0

:cleanup_stale_pid
set "PID_FILE=%~1"
if not exist "%PID_FILE%" exit /b 0
set "PID_VALUE="
for /f "usebackq delims=" %%i in ("%PID_FILE%") do set "PID_VALUE=%%i"
if not defined PID_VALUE (
    del /f /q "%PID_FILE%" >nul 2>nul
    exit /b 0
)
tasklist /FI "PID eq %PID_VALUE%" | findstr /R /C:" %PID_VALUE% " >nul
if errorlevel 1 (
    del /f /q "%PID_FILE%" >nul 2>nul
) else (
    echo [ERROR] 已存在运行中的进程，PID: %PID_VALUE%，请先执行 stop_app.bat
    exit /b 1
)
exit /b 0

:ensure_port_free
set "TARGET_PORT=%~1"
set "SERVICE_NAME=%~2"
set "PORT_PID="
for /f "tokens=5" %%i in ('netstat -ano ^| findstr /R /C:":%TARGET_PORT% .*LISTENING"') do (
    set "PORT_PID=%%i"
    goto :ensure_port_found
)
goto :ensure_port_done
:ensure_port_found
echo [ERROR] %SERVICE_NAME% 端口 %TARGET_PORT% 已被占用，PID: !PORT_PID!，请先执行 stop_app.bat 或手动释放端口
exit /b 1
:ensure_port_done
exit /b 0

:wait_for_port
set "WAIT_PORT=%~1"
set "WAIT_COUNT=%~2"
set /a WAIT_INDEX=0
:wait_port_loop
for /f "tokens=5" %%i in ('netstat -ano ^| findstr /R /C:":%WAIT_PORT% .*LISTENING"') do exit /b 0
set /a WAIT_INDEX+=1
if %WAIT_INDEX% geq %WAIT_COUNT% exit /b 1
ping -n 2 127.0.0.1 >nul 2>nul
goto :wait_port_loop
