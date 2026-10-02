#define MyAppName "Tech OCR"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Tech OCR"
#define MyAppExeName "TechOCR.exe"

[Setup]
AppId={{7D02E48C-2024-4A56-A3BA-4ACB6C18A402}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\TechOCR
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist-installer
OutputBaseFilename=TechOCR-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Ish stolida yorliq yaratish"; GroupDescription: "Yorliqlar:"
Name: "aihelper"; Description: "Lokal AI yordamchini o'rnatish (internet va qo'shimcha disk joyi kerak)"; GroupDescription: "AI yordamchi:"; Flags: checkedonce
Name: "legacydoc"; Description: "Eski DOC fayllari uchun LibreOffice o'rnatish"; GroupDescription: "Qo'shimcha format:"; Flags: checkedonce

[Files]
Source: "..\dist\TechOCR\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "install-ai.ps1"; DestDir: "{app}\tools"; Flags: ignoreversion
Source: "install-libreoffice.ps1"; DestDir: "{app}\tools"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\tools\install-ai.ps1"""; Description: "Ollama va AI modelini tayyorlash"; Flags: postinstall skipifsilent; Tasks: aihelper
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\tools\install-libreoffice.ps1"""; Description: "LibreOffice'ni tayyorlash"; Flags: postinstall skipifsilent; Tasks: legacydoc
Filename: "{app}\{#MyAppExeName}"; Description: "{#MyAppName} dasturini ishga tushirish"; Flags: nowait postinstall skipifsilent
