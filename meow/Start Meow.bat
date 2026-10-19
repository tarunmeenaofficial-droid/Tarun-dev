@echo off
title Start Meow
cd /d "%~dp0"
python start_meow.py %*
if errorlevel 9009 (echo Python is not installed - get it from python.org ^(tick "Add to PATH"^) & pause)
