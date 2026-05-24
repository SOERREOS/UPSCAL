#define MyAppName "UPSCAL"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "REOS"
#define MyAppExeName "UPSCAL.exe"

[Setup]
AppId={{2E7CC290-7F89-40BF-AB0E-F6C3E5A707B8}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist_installer
OutputBaseFilename=UPSCAL_Setup_v{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=UPSCAL.ico
WizardImageFile=UPSCAL_WizardLarge.bmp
WizardSmallImageFile=UPSCAL_WizardSmall.bmp
ShowLanguageDialog=auto
LanguageDetectionMethod=locale
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\UPSCAL.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[CustomMessages]
english.LaunchUPSCAL=Launch UPSCAL
korean.LaunchUPSCAL=UPSCAL 실행

[Files]
Source: "..\dist_app\UPSCAL\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "UPSCAL.ico"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
Type: files; Name: "{group}\{#MyAppName}.lnk"
Type: files; Name: "{autodesktop}\{#MyAppName}.lnk"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\UPSCAL.ico"; IconIndex: 0
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\UPSCAL.ico"; IconIndex: 0

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchUPSCAL}"; Flags: nowait postinstall skipifsilent

[Code]
const
  C_BG = $000B0808;
  C_TEXT = $00F2EDEC;
  C_MUTED = $00AB9B9A;

procedure StyleWizard;
begin
  WizardForm.Color := C_BG;
  WizardForm.MainPanel.Color := C_BG;
  WizardForm.PageNameLabel.Font.Color := C_TEXT;
  WizardForm.PageNameLabel.Font.Style := [fsBold];
  WizardForm.PageDescriptionLabel.Font.Color := C_MUTED;
  WizardForm.WelcomeLabel1.Font.Color := C_TEXT;
  WizardForm.WelcomeLabel1.Font.Style := [fsBold];
  WizardForm.WelcomeLabel2.Font.Color := C_MUTED;
  WizardForm.FinishedHeadingLabel.Font.Color := C_TEXT;
  WizardForm.FinishedHeadingLabel.Font.Style := [fsBold];
  WizardForm.FinishedLabel.Font.Color := C_MUTED;
  WizardForm.Bevel.Visible := False;
end;

procedure InitializeWizard;
begin
  StyleWizard;
end;
