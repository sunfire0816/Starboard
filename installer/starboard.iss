; Inno Setup script for Starboard. build.bat runs it with /DAppVersion=<version>.
#ifndef AppVersion
  #define AppVersion "0.0"
#endif

[Setup]
AppId={{7B1E4C2A-5D3F-4E8B-9A61-2C0F8D7E3B54}
AppName=Starboard
AppVersion={#AppVersion}
AppVerName=Starboard {#AppVersion}
AppPublisher=BSquaredTV
; Installs for the current user, no admin prompt, into a folder Starboard can write its user data to.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\Starboard
DefaultGroupName=Starboard
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=StarboardSetup-{#AppVersion}
SetupIconFile=starboard.ico
UninstallDisplayIcon={app}\Starboard.exe
LicenseFile=..\LICENSE-GPL3.txt
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Messages]
WelcomeLabel2=This will install Starboard [ver], a free Star Citizen companion.%n%nStarboard is an unofficial fan tool, not affiliated with, endorsed by or sponsored by the Cloud Imperium group of companies. Star Citizen, Squadron 42, Roberts Space Industries and Cloud Imperium are registered trademarks of Cloud Imperium Rights LLC.

[Files]
Source: "..\dist\Starboard\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Starboard"; Filename: "{app}\Starboard.exe"
Name: "{group}\Uninstall Starboard"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Starboard"; Filename: "{app}\Starboard.exe"

[Run]
Filename: "{app}\Starboard.exe"; Description: "Start Starboard"; Flags: nowait postinstall skipifsilent

; The user folder (settings, hangar, ledger, plans, game log history) is never touched by
; installing a new version. Uninstalling leaves it too, so a reinstall picks up where you left off.
