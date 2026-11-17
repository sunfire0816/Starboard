MAKING STARBOARD.EXE AND THE INSTALLER

1. Install Python 3 from python.org (tick "Add python.exe to PATH").
2. Optional, for the installer: install Inno Setup (version 6 or 7) from https://jrsoftware.org/isdl.php
3. Double-click build.bat in this folder.

You get:
  dist\Starboard\Starboard.exe      runs without Python, keep the whole folder together
  dist\StarboardSetup-<version>.exe one file to give to other players (with Inno Setup)

The installer puts Starboard in your user's Programs folder, with a Start menu entry and an
optional desktop shortcut. No admin prompt. Your data lives in %LOCALAPPDATA%\Starboard, so new versions,
rebuilds and uninstalling never touch it.

RELEASING AN UPDATE
1. Raise APP_VERSION at the top of sc_locator.py (for example 11.4).
2. Run build.bat.
3. On GitHub, make a new release with the tag v11.4 and attach StarboardSetup-11.4.exe.
   Write what changed in the release notes; Starboard shows them in the update message.
Everyone who has your project name under SETTINGS > STARBOARD UPDATES is told the next
time they start Starboard.
