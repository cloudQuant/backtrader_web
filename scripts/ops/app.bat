@echo off
chcp 65001 >nul
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "PROJECT_ROOT=%SCRIPT_DIR%\.."
set "PID_DIR=%PROJECT_ROOT%\.pids"

if /I "%~1"=="start" goto :start
if /I "%~1"=="stop" goto :stop
if /I "%~1"=="restart" goto :restart
if /I "%~1"=="status" goto :status
if /I "%~1"=="help" goto :usage
if /I "%~1"=="--help" goto :usage
if /I "%~1"=="-h" goto :usage
if "%~1"=="" goto :usage

echo Unknown command: %~1
call :usage
exit /b 2

:start
call "%SCRIPT_DIR%\windows\start_app.bat" %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:stop
call "%SCRIPT_DIR%\windows\stop_app.bat" %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:restart
call "%SCRIPT_DIR%\windows\restart_app.bat" %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:status
call :service_status backend "%PID_DIR%\backend.pid"
call :service_status frontend "%PID_DIR%\frontend.pid"
exit /b 0

:service_status
set "SERVICE_NAME=%~1"
set "PID_FILE=%~2"
if not exist "%PID_FILE%" (
    echo %SERVICE_NAME%: stopped ^(no PID file^)
    exit /b 0
)
set "PID_VALUE="
for /f "usebackq delims=" %%i in ("%PID_FILE%") do set "PID_VALUE=%%i"
if not defined PID_VALUE (
    echo %SERVICE_NAME%: stale PID file ^(empty^)
    exit /b 0
)
tasklist /FI "PID eq %PID_VALUE%" | findstr /R /C:" %PID_VALUE% " >nul
if errorlevel 1 (
    echo %SERVICE_NAME%: stale PID file ^(%PID_VALUE%^)
) else (
    echo %SERVICE_NAME%: running ^(PID: %PID_VALUE%^)
)
exit /b 0

:usage
echo Usage: scripts\app.bat ^<start^|stop^|restart^|status^>
echo.
echo Commands:
echo   start    Start backend and frontend development services
echo   stop     Stop backend and frontend development services
echo   restart  Stop and then start development services
echo   status   Show PID-file based service status
exit /b 0
