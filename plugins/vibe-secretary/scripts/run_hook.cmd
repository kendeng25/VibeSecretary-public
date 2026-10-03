@echo off
setlocal
if not defined PLUGIN_ROOT (
  echo VibeSecretary Hook launcher: PLUGIN_ROOT is not set. 1>&2
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PLUGIN_ROOT%\scripts\run_hook.ps1" -Hook "%~1"
exit /b %ERRORLEVEL%