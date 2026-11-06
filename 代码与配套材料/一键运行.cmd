@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -c "import numpy,scipy,sklearn,jieba,matplotlib" >nul 2>&1
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -B "运行实验.py" --mode classroom
if errorlevel 1 goto failed
echo Completed. Results are in the timestamped output folder.
pause
exit /b 0
:failed
echo Failed. Please keep the log and follow README.md.
pause
exit /b 1
