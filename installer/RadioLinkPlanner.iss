#define MyAppName "PU2PTU - Radio Link Planner"
#define MyAppVersion "0.6.2"
#define MyAppPublisher "Mario Pin - PU2PTU"
#define MyAppExeName "RadioLinkPlanner.exe"
#define MyAppIconName "RadioLinkPlanner-" + MyAppVersion + ".ico"
#define MyAppId "{{5F814E4D-B379-5608-A6DF-5FDCCDB9BBC7}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=Instalador do {#MyAppName}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}.0
DefaultDirName={autopf}\Radio Link Planner
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\installer-output
OutputBaseFilename=RadioLinkPlanner-{#MyAppVersion}-Windows-x64-Setup
Compression=lzma2/max
SolidCompression=yes
SetupIconFile=..\assets\app-icon.ico
WizardStyle=modern
SetupLogging=yes
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\{#MyAppIconName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\RadioLinkPlanner\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\assets\app-icon.ico"; DestDir: "{app}"; DestName: "{#MyAppIconName}"; Flags: ignoreversion

[InstallDelete]
Type: files; Name: "{autoprograms}\Radio Link Planner.lnk"
Type: files; Name: "{autodesktop}\Radio Link Planner.lnk"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppIconName}"; IconIndex: 0; AppUserModelID: "MarioPin.RadioLinkPlanner"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppIconName}"; IconIndex: 0; AppUserModelID: "MarioPin.RadioLinkPlanner"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

