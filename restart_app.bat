@echo off
chcp 65001 >nul
setlocal EnableExtensions
set "SCRIPT_DIR=%~dp0"
set "LOG_DIR=%SCRIPT_DIR%logs"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

if /I "%~1"=="__run__" goto :run
if /I "%~1"=="__sync__" goto :run

set "RUN_TOKEN=%RANDOM%_%RANDOM%"
set "ASYNC_LOG=%LOG_DIR%\restart_app.%RUN_TOKEN%.async.log"
type nul > "%ASYNC_LOG%"

echo ======================================
echo   Backtrader Web - 后台重启中
echo ======================================
echo.
echo [INFO] 已提交到后台执行
echo [INFO] 实时输出窗口将单独打开，当前终端可继续使用
echo [INFO] 日志文件: %ASYNC_LOG%

powershell -NoProfile -ExecutionPolicy Bypass -Command "$log = [System.IO.Path]::GetFullPath('%ASYNC_LOG%'); $script = [System.IO.Path]::GetFullPath('%~f0'); $runner = '[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [Console]::OutputEncoding; $utf8 = New-Object System.Text.UTF8Encoding($false); [System.IO.File]::WriteAllText(''' + $log + ''', '''', $utf8); & ''' + $script + ''' __sync__ 2>&1 | ForEach-Object { $line = $_.ToString(); [System.IO.File]::AppendAllText(''' + $log + ''', $line + [Environment]::NewLine, $utf8); Write-Output $line }; Write-Host ''''; Write-Host ''[INFO] 重启脚本已执行完成，可关闭此窗口'''; Start-Process -WindowStyle Normal -FilePath 'powershell.exe' -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-NoExit','-Command',$runner | Out-Null"

endlocal
exit /b 0

:run
echo ======================================
echo   Backtrader Web - 重启项目
echo ======================================
echo.

call "%SCRIPT_DIR%stop_app.bat" __sync__
if errorlevel 1 (
    echo [ERROR] stop_app.bat 执行失败
    endlocal
    exit /b 1
)

timeout /t 2 /nobreak >nul 2>nul

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
