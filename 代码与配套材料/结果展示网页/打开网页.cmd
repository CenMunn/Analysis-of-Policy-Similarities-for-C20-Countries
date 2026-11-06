@echo off
chcp 65001 >nul
if not exist "%~dp0index.html" (
  echo Cannot find index.html. Please extract the whole folder first.
  pause
  exit /b 1
)
start "" "%~dp0index.html"
