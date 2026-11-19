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
VersionInfoVersion={#MyAppVersion}.1
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
OutputBaseFilename=RadioLinkPlanner-{#MyAppVersion}-Windows-x64-Setup-r2
Compression=lzma2/max
SolidCompression=yes
LicenseFile=..\legal\EVALUATION-TERMS.en.txt
SetupIconFile=..\assets\app-icon.ico
WizardStyle=modern
SetupLogging=yes
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\{#MyAppIconName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"; LicenseFile: "..\legal\EVALUATION-TERMS.pt-BR.txt"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"; LicenseFile: "..\legal\EVALUATION-TERMS.es.txt"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"; LicenseFile: "..\legal\EVALUATION-TERMS.fr.txt"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"; LicenseFile: "..\legal\EVALUATION-TERMS.de.txt"

[Messages]
english.WizardLicense=Terms of Use
english.LicenseAccepted=I have read and agree to the terms of use
english.LicenseNotAccepted=I do not agree to the terms of use
brazilianportuguese.WizardLicense=Termos de Uso
brazilianportuguese.LicenseAccepted=Li e concordo com os termos de uso
brazilianportuguese.LicenseNotAccepted=Não concordo com os termos de uso
spanish.WizardLicense=Términos de uso
spanish.LicenseAccepted=He leído y acepto los términos de uso
spanish.LicenseNotAccepted=No acepto los términos de uso
french.WizardLicense=Conditions d’utilisation
french.LicenseAccepted=J’ai lu et j’accepte les conditions d’utilisation
french.LicenseNotAccepted=Je n’accepte pas les conditions d’utilisation
german.WizardLicense=Nutzungsbedingungen
german.LicenseAccepted=Ich habe die Nutzungsbedingungen gelesen und akzeptiere sie
german.LicenseNotAccepted=Ich akzeptiere die Nutzungsbedingungen nicht

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\RadioLinkPlanner\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\assets\app-icon.ico"; DestDir: "{app}"; DestName: "{#MyAppIconName}"; Flags: ignoreversion
Source: "..\legal\EVALUATION-TERMS.*.txt"; DestDir: "{app}\licenses"; Flags: ignoreversion

[InstallDelete]
Type: files; Name: "{autoprograms}\Radio Link Planner.lnk"
Type: files; Name: "{autodesktop}\Radio Link Planner.lnk"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppIconName}"; IconIndex: 0; AppUserModelID: "MarioPin.RadioLinkPlanner"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppIconName}"; IconIndex: 0; AppUserModelID: "MarioPin.RadioLinkPlanner"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeSetup(): Boolean;
begin
  Result := (not WizardSilent) or (ExpandConstant('{param:ACCEPTTERMS|0}') = '1');
  if not Result then
    Log('Silent installation requires /ACCEPTTERMS=1.');
end;

