@echo off
rem ARGUS MCP launcher: runs the server from this folder so .env loads.
rem Point your IDE's MCP config "command" at this file.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  .venv\Scripts\python.exe -m argus
) else (
  python -m argus
)
