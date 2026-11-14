@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  python -m stylekit --workspace "%~dp0workspace" serve
) else (
  py -3 -m stylekit --workspace "%~dp0workspace" serve
)
