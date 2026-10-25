@echo off
rem vdo engine launcher: vdo.bat new ^| plan ^| status ^| import ^| sheet ^| build ^| doctor ^| sfx-list
setlocal
set "VDO_HOME=%~dp0"
set "PY=%VDO_HOME%.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
set "PYTHONPATH=%VDO_HOME%;%PYTHONPATH%"
set "PYTHONUTF8=1"
"%PY%" -m vdo %*
exit /b %ERRORLEVEL%
