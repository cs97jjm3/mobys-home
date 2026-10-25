@echo off
rem Starts the Moby's Home helper, which shares this computer's processor, memory and disk figures.
rem Keep it in the same folder as moby_agent.py.
title Moby's Home helper
cd /d "%~dp0"
:loop
py moby_agent.py
timeout /t 30 /nobreak >nul
goto loop
