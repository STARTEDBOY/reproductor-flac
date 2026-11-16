@echo off
REM Lanza el reproductor FLAC en Windows.
cd /d "%~dp0"
py -3 main.py %*
if errorlevel 1 python main.py %*
