@echo off
REM Yad2 Apartment Crawler - Run via Windows Task Scheduler every 15 minutes
REM Setup: Task Scheduler -> Create Task -> Trigger: every 15 min -> Action: run this bat

cd /d "%~dp0"
python main.py
