@echo off
if not exist "%~dp0..\Mockups" mkdir "%~dp0..\Mockups"
start "" explorer "%~dp0..\Mockups"
