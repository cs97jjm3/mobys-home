@echo off
rem Starts Moby's Home and restarts it if it ever stops.
rem Keep this file in the same folder as home_hub.py.
rem Run it as "start_home.bat log" to write everything to home.log instead.

title Moby's Home
cd /d "%~dp0"

:loop
if /i "%~1"=="log" goto logged

echo Starting Moby's Home at %date% %time%
py home_hub.py
echo.
echo Moby's Home stopped. Starting it again in 30 seconds - close this window to stop it for good.
goto wait

:logged
echo Starting Moby's Home at %date% %time% >> home.log
py -u home_hub.py >> home.log 2>&1
echo Moby's Home stopped at %date% %time%, starting again in 30 seconds >> home.log

:wait
timeout /t 30 /nobreak >nul
goto loop
