@echo off
title Project IRIS Launcher
cd /d "%~dp0"
start "" ".\.venv\Scripts\python.exe" "open_dashboard.py"
exit
