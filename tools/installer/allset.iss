; Maya Workflow Kit Windows installer — DRAFT.
; Not built, not signed, not published: compiling needs Inno Setup 6 (https://jrsoftware.org/isinfo.php),
; and a public .exe needs an Authenticode signature (SmartScreen) — neither is done yet.
; The work is done by allset_setup.ps1 (tested by tools/installer_check.py);
; this script only shows pages and calls it.
;
; Build (after `python tools/build.py`):
;   ISCC.exe /DAppVersion=0.1.0 /DKitZip=..\..\dist\maya-workflow-kit-0.1.0.zip tools\installer\allset.iss
;
; Per-user install, no admin rights: the kit goes into each chosen Blender version's user extensions
; folder (%APPDATA%\Blender Foundation\Blender\<x.y>\extensions\user_default) through Blender itself.
; The setup folder ({app}) only keeps the zip, the helper scripts and the list of Blender versions it
; installed for, which the uninstaller uses to remove the kit the way Preferences > Remove does
; (the user's keymap, theme and preferences come back).

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#ifndef KitZip
  #define KitZip "..\..\dist\maya-workflow-kit-" + AppVersion + ".zip"
#endif

[Setup]
AppId={{CFBBD6AA-65FB-4121-9094-10EF64C2A40D}
AppName=Maya Workflow Kit
AppVersion={#AppVersion}
AppPublisher=5hyuns
; Autodesk trademark footnote.
AppCopyright=GPL-3.0-or-later. Autodesk and Maya are trademarks of the Autodesk group of companies; this project is not affiliated with Autodesk.
DefaultDirName={localappdata}\Maya Workflow Kit
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=MayaWorkflowKitSetup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\..\LICENSE
UninstallDisplayName=Maya Workflow Kit (for Blender)
; SignTool=...   ; only with a code-signing certificate (not set up)

[Files]
Source: "{#KitZip}"; DestDir: "{app}"; DestName: "maya-workflow-kit.zip"
Source: "allset_setup.ps1"; DestDir: "{app}"
Source: "blender_helper.py"; DestDir: "{app}"

[Run]
; The install itself runs from CurStepChanged (it needs the chosen Blender list).

[UninstallRun]
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\allset_setup.ps1"" -Uninstall -TargetsFile ""{app}\targets.txt"""; \
  Flags: runhidden waituntilterminated; RunOnceId: "RemoveKit"

[Code]
var
  BlenderPage: TInputOptionWizardPage;
  MayaPage: TInputOptionWizardPage;
  BlenderExes: TArrayOfString;

function SetupScript(): String;
begin
  Result := ExpandConstant('{tmp}\allset_setup.ps1');
end;

function RunSetup(const Args: String; var Code: Integer): Boolean;
begin
  Result := Exec('powershell.exe',
    '-NoProfile -ExecutionPolicy Bypass -File "' + SetupScript() + '" ' + Args,
    '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

procedure FindBlender();
var
  Lines: TArrayOfString;
  ListFile, Line, Exe, Version, Source, Compatible: String;
  I, P, Code, N: Integer;
begin
  ExtractTemporaryFile('allset_setup.ps1');
  ExtractTemporaryFile('blender_helper.py');
  ListFile := ExpandConstant('{tmp}\blender_list.txt');
  Exec('cmd.exe', '/c powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + SetupScript() +
       '" -List -Plain > "' + ListFile + '"', '', SW_HIDE, ewWaitUntilTerminated, Code);
  SetArrayLength(BlenderExes, 0);
  if not LoadStringsFromFile(ListFile, Lines) then Exit;
  N := 0;
  for I := 0 to GetArrayLength(Lines) - 1 do
  begin
    Line := Lines[I];                       { exe|version|source|compatible }
    P := Pos('|', Line); if P = 0 then Continue;
    Exe := Copy(Line, 1, P - 1); Delete(Line, 1, P);
    P := Pos('|', Line); Version := Copy(Line, 1, P - 1); Delete(Line, 1, P);
    P := Pos('|', Line); Source := Copy(Line, 1, P - 1); Delete(Line, 1, P);
    Compatible := Line;
    if Compatible <> 'True' then Continue;  { too old/new, or a Store install (install from inside Blender) }
    SetArrayLength(BlenderExes, N + 1);
    BlenderExes[N] := Exe;
    BlenderPage.Add('Blender ' + Version + '   (' + Exe + ')');
    BlenderPage.Values[N] := (N = 0);       { newest checked }
    N := N + 1;
  end;
end;

procedure InitializeWizard();
begin
  BlenderPage := CreateInputOptionPage(wpLicense, 'Blender versions',
    'Which Blender should get Maya Workflow Kit?',
    'Maya Workflow Kit is installed into each checked Blender version (each version keeps its own settings). ' +
    'Close those Blender versions before you continue. A portable Blender that is not listed: ' +
    'drag maya-workflow-kit.zip into its window instead.', False, False);
  MayaPage := CreateInputOptionPage(BlenderPage.ID, 'Maya mode',
    'How should Blender look after the install?', '', False, False);
  MayaPage.Add('Make Blender Maya now: Maya layout, theme and keymap (switch back any time with the Maya | Blender button)');
  MayaPage.Values[0] := True;
  FindBlender();
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  I: Integer;
  Any: Boolean;
begin
  Result := True;
  if CurPageID = BlenderPage.ID then
  begin
    Any := False;
    for I := 0 to GetArrayLength(BlenderExes) - 1 do
      if BlenderPage.Values[I] then Any := True;
    if not Any then
    begin
      MsgBox('No Blender 4.2 - 5.2 selected (or found). Install Blender from blender.org first, ' +
             'or drag maya-workflow-kit.zip into a running Blender.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  I, Code: Integer;
  Targets, Args: String;
begin
  if CurStep <> ssPostInstall then Exit;
  Targets := '';
  for I := 0 to GetArrayLength(BlenderExes) - 1 do
    if BlenderPage.Values[I] then Targets := Targets + BlenderExes[I] + ';';
  Args := '-Install -Zip "' + ExpandConstant('{app}\maya-workflow-kit.zip') + '" -Blender "' + Targets + '"' +
          ' -Record "' + ExpandConstant('{app}\targets.txt') + '"';
  if MayaPage.Values[0] then Args := Args + ' -MakeMaya';
  if not RunSetup(Args, Code) or (Code <> 0) then
  begin
    if Code = 3 then
      MsgBox('A selected Blender is running. Close it and run the setup again.', mbError, MB_OK)
    else
      MsgBox('Installing Maya Workflow Kit into Blender failed (code ' + IntToStr(Code) + '). ' +
             'You can still drag maya-workflow-kit.zip into Blender: ' + ExpandConstant('{app}'), mbError, MB_OK);
  end;
end;
