@echo off
chcp 65001 >nul
setlocal EnableExtensions

echo ======================================
echo   Backtrader Web - 重启项目
echo ======================================
echo.

cmd /c "%~dp0stop_app.bat"

timeout /t 2 /nobreak >nul 2>nul

cmd /c "%~dp0start_app.bat"

echo.
echo [OK] 重启完成
endlocal
exit /b 0
