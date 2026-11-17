@echo off
rem Builds Starboard.exe and, if Inno Setup is installed, StarboardSetup-<version>.exe
rem Run it from anywhere: double-click it in the installer folder.
setlocal
cd /d "%~dp0.."

where py >nul 2>nul && (set PY=py -3) || (set PY=python)

for /f "tokens=2 delims==" %%v in ('findstr /b /c:"APP_VERSION = " sc_locator.py') do set VER=%%~v
set VER=%VER: =%
set VER=%VER:"=%
echo Building Starboard %VER%

echo Installing the build tools (PyInstaller, zstandard)...
%PY% -m pip install --upgrade pyinstaller zstandard >nul || goto :fail

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

%PY% -m PyInstaller --noconfirm --clean --windowed --name Starboard ^
  --icon installer\starboard.ico ^
  --hidden-import zstandard ^
  --exclude-module numpy --exclude-module PIL ^
  sc_locator.py || goto :fail

echo Copying data and documents...
xcopy /e /i /q /y data dist\Starboard\data >nul || goto :fail
if exist dist\Starboard\data\backups rmdir /s /q dist\Starboard\data\backups
copy /y README.md dist\Starboard\ >nul
copy /y LICENSE-GPL3.txt dist\Starboard\ >nul

set ISCC=
rem Inno Setup 7 or 6, wherever it was installed
for %%V in (6 7) do (
  if exist "%ProgramFiles(x86)%\Inno Setup %%V\ISCC.exe" set ISCC="%ProgramFiles(x86)%\Inno Setup %%V\ISCC.exe"
  if exist "%ProgramFiles%\Inno Setup %%V\ISCC.exe" set ISCC="%ProgramFiles%\Inno Setup %%V\ISCC.exe"
  if exist "%LocalAppData%\Programs\Inno Setup %%V\ISCC.exe" set ISCC="%LocalAppData%\Programs\Inno Setup %%V\ISCC.exe"
)
if not defined ISCC for /f "delims=" %%I in ('where iscc 2^>nul') do set ISCC="%%I"
if not defined ISCC (
  echo.
  echo Starboard.exe is ready in dist\Starboard
  start "" explorer "%CD%\dist\Starboard"
  echo To also make the installer, install Inno Setup from https://jrsoftware.org/isdl.php and run this again.
  goto :done
)
%ISCC% /DAppVersion=%VER% installer\starboard.iss || goto :fail
echo.
echo Installer ready: dist\StarboardSetup-%VER%.exe
start "" explorer "%CD%\dist"
goto :done

:fail
echo.
echo The build stopped with an error. Scroll up to see what went wrong.
:done
pause
