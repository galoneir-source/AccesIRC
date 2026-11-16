; Instalador de AccesIRC para Inno Setup 6.3 o posterior.
; No se compila a mano: lo hace crear_exe.bat, que le pasa la versión con /DMyVersion=...

#ifndef MyVersion
  #define MyVersion "0.0.0"
#endif

[Setup]
AppId={{F6518084-6D0E-463D-9FAC-F1D526B9F1FF}
AppName=AccesIRC
AppVersion={#MyVersion}
AppVerName=AccesIRC {#MyVersion}
AppPublisher=Daniel Villalón y José Ángel Ortiz
VersionInfoVersion={#MyVersion}
VersionInfoDescription=Instalador de AccesIRC
; Se instala solo para el usuario actual, en %LOCALAPPDATA%\Programs\AccesIRC:
; no pide permisos de administrador ni hace preguntas de más.
PrivilegesRequired=lowest
DefaultDirName={autopf}\AccesIRC
DefaultGroupName=AccesIRC
DisableProgramGroupPage=yes
DisableWelcomePage=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=dist
OutputBaseFilename=AccesIRC-{#MyVersion}-instalador
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\AccesIRC.exe
UninstallDisplayName=AccesIRC
; Si AccesIRC está abierto al actualizar, el instalador ofrece cerrarlo.
CloseApplications=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el &escritorio"; GroupDescription: "Accesos directos:"

[InstallDelete]
; Al actualizar, se borran las bibliotecas de la versión anterior para no mezclarlas.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "dist\AccesIRC\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\AccesIRC"; Filename: "{app}\AccesIRC.exe"
Name: "{autoprograms}\Léeme de AccesIRC"; Filename: "{app}\LEEME.txt"
Name: "{autodesktop}\AccesIRC"; Filename: "{app}\AccesIRC.exe"; Tasks: escritorio

[Run]
Filename: "{app}\AccesIRC.exe"; Description: "Abrir AccesIRC ahora"; Flags: nowait postinstall skipifsilent

; La configuración y las conversaciones están en %APPDATA%\AccesIRC y no se borran al
; desinstalar, para no perder las contraseñas ni los registros si se reinstala.
