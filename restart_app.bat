@echo off
chcp 65001 >nul
setlocal EnableExtensions
set "SCRIPT_DIR=%~dp0"
set "LOG_DIR=%SCRIPT_DIR%logs"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo ======================================
echo   Backtrader Web - 重启项目
echo ======================================
echo.

echo [INFO] 清理旧日志...
del /f /q "%LOG_DIR%\restart_app.*.async.log" >nul 2>nul
del /f /q "%LOG_DIR%\restart_app.async.log" >nul 2>nul
del /f /q "%LOG_DIR%\start_app.*.async.log" >nul 2>nul
del /f /q "%LOG_DIR%\stop_app.*.async.log" >nul 2>nul
del /f /q "%LOG_DIR%\backend.out.log" >nul 2>nul
del /f /q "%LOG_DIR%\backend.err.log" >nul 2>nul
del /f /q "%LOG_DIR%\frontend.out.log" >nul 2>nul
del /f /q "%LOG_DIR%\frontend.err.log" >nul 2>nul
del /f /q "%LOG_DIR%\test_backend.out.log" >nul 2>nul
del /f /q "%LOG_DIR%\test_backend.err.log" >nul 2>nul
echo [OK] 旧日志已清理
echo.

call "%SCRIPT_DIR%stop_app.bat" __sync__
if errorlevel 1 (
    echo [ERROR] stop_app.bat 执行失败
    endlocal
    exit /b 1
)

ping -n 3 127.0.0.1 >nul 2>nul

call "%SCRIPT_DIR%start_app.bat" __sync__
if errorlevel 1 (
    echo [ERROR] start_app.bat 执行失败
    endlocal
    exit /b 1
)

echo.
echo [OK] 重启完成
endlocal
exit /b 0
