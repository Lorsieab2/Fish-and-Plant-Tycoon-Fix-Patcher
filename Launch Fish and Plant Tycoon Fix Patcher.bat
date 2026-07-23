@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "src\tycoon_fix_patcher_gui.py"
) else (
  python "src\tycoon_fix_patcher_gui.py"
)
if errorlevel 1 pause
