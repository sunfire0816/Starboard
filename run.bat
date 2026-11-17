@echo off
cd /d "%~dp0"
where py >nul 2>nul && (start "" pyw -3 sc_locator.py & exit /b)
where pythonw >nul 2>nul && (start "" pythonw sc_locator.py & exit /b)
where python >nul 2>nul && (python sc_locator.py & exit /b)
echo Python 3 was not found. Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
pause
