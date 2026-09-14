@echo off
cd /d %~dp0
if not exist .venv\Scripts\activate.bat (
  echo Please run setup.bat first.
  pause
  exit /b 1
)
call .venv\Scripts\activate
py app.py
