@echo off
powershell.exe -NoLogo -NoProfile -File "%~dp0Start-AUTOZS-Orders.ps1"
if errorlevel 1 pause
