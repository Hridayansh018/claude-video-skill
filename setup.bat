@echo off
rem One-click setup: Python packages, ffmpeg, Kokoro voice model, Claude skill.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
echo.
pause
