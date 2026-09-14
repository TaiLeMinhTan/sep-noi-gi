@echo off
cd /d %~dp0
if not exist .venv (
  py -m venv .venv
)
call .venv\Scripts\activate
py -m pip install -r requirements.txt
if not exist .env copy .env.example .env
 echo.
 echo Setup complete. Open .env and add OPENAI_API_KEY, then run run.bat
pause
