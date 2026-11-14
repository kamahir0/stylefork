@echo off
if "%~1"=="" (
  echo Usage: start.bat "C:\path\to\creation-project"
  exit /b 2
)
set "STYLEFORK_PY=python"
where py >nul 2>nul
if not errorlevel 1 set "STYLEFORK_PY=py -3"
%STYLEFORK_PY% -B "%~dp0run.py" --workspace "%~1" init
if errorlevel 1 exit /b 1
%STYLEFORK_PY% -B "%~dp0run.py" --workspace "%~1" serve
