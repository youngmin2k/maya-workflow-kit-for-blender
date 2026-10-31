<#
.SYNOPSIS
  Maya Workflow Kit setup helper for Windows: find Blender installs, install / uninstall the extension.
  Draft for the installer; called by allset.iss, usable on its own.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File allset_setup.ps1 -List
  powershell -ExecutionPolicy Bypass -File allset_setup.ps1 -Install -Zip maya-workflow-kit-0.2.0.zip [-Blender "C:\...\blender.exe"] [-MakeMaya]
  powershell -ExecutionPolicy Bypass -File allset_setup.ps1 -Uninstall [-Blender "C:\...\blender.exe"]

.NOTES
  Every action goes through Blender itself:
    install   = blender --command extension install-file -r user_default --enable <zip>
    Make Maya = blender -b --python blender_helper.py -- make   (layout template, theme, splash off)
    uninstall = blender -b --python blender_helper.py -- remove (Preferences > Remove: the kit's
                unregister restores the user's keymap, theme and preferences first)
  Each Blender version has its own user config (%APPDATA%\Blender Foundation\Blender\<x.y>), so the kit
  is installed per selected version. Blender must not be running for that version: it would save its
  old preferences over the change when it quits. No network, no admin rights (per-user install).
  -Blender takes one or more blender.exe paths ("a;b" also works: Inno Setup passes one string).
  -Record FILE (install) writes the Blender paths it installed for; -TargetsFile FILE (uninstall) reads them.
  -Plain (with -List) prints "exe|version|source|compatible" lines for the Inno Setup page.
  Exit codes: 0 ok, 1 failure, 2 no compatible Blender found, 3 Blender is running.
#>
[CmdletBinding()]
param(
    [switch]$List,
    [switch]$Install,
    [switch]$Uninstall,
    [switch]$MakeMaya,
    [string[]]$Blender = @(),
    [string]$Zip = "",
    [switch]$Json,
    [switch]$Plain,
    [string]$Record = "",
    [string]$TargetsFile = ""
)

$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Helper = Join-Path $Here "blender_helper.py"
# Supported range (blender_manifest.toml blender_version_min / _max, max exclusive); read from the zip when given.
$script:MinVersion = [version]"4.2"
$script:MaxVersion = [version]"5.3"

function Read-ManifestRange([string]$ZipPath) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        $entry = $archive.Entries | Where-Object { $_.FullName -eq "blender_manifest.toml" } | Select-Object -First 1
        if (-not $entry) { throw "blender_manifest.toml not found in $ZipPath" }
        $reader = New-Object System.IO.StreamReader($entry.Open())
        $text = $reader.ReadToEnd()
        $reader.Close()
    } finally { $archive.Dispose() }
    if ($text -match '(?m)^blender_version_min\s*=\s*"(\d+\.\d+)') { $script:MinVersion = [version]$Matches[1] }
    if ($text -match '(?m)^blender_version_max\s*=\s*"(\d+\.\d+)') { $script:MaxVersion = [version]$Matches[1] }
}

function Get-VersionFromPath([string]$Exe) {
    # "...\Blender 4.5\blender.exe" or the version folder next to blender.exe ("4.5\")
    $dir = Split-Path -Parent $Exe
    $sub = Get-ChildItem -LiteralPath $dir -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^\d+\.\d+$' } | Sort-Object { [version]$_.Name } | Select-Object -Last 1
    if ($sub) { return [version]$sub.Name }
    if ($dir -match '(\d+\.\d+)') { return [version]$Matches[1] }
    return $null
}

function Find-Blender {
    $found = @{}
    # 1. official MSI installs: Uninstall entries named "Blender" with InstallLocation
    $keys = @("HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
              "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
              "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*")
    foreach ($e in (Get-ItemProperty $keys -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -like "Blender*" })) {
        if ($e.InstallLocation) {
            $exe = Join-Path $e.InstallLocation "blender.exe"
            if (Test-Path -LiteralPath $exe) { $found[$exe.ToLower()] = @{ Exe = $exe; Source = "installer" } }
        }
    }
    # 2. default folders (zip installs unpacked there, older MSI)
    foreach ($root in @("$env:ProgramFiles\Blender Foundation", "${env:ProgramFiles(x86)}\Blender Foundation")) {
        if ($root -and (Test-Path -LiteralPath $root)) {
            foreach ($exe in (Get-ChildItem -LiteralPath $root -Filter blender.exe -Recurse -Depth 1 -ErrorAction SilentlyContinue)) {
                if (-not $found.ContainsKey($exe.FullName.ToLower())) { $found[$exe.FullName.ToLower()] = @{ Exe = $exe.FullName; Source = "folder" } }
            }
        }
    }
    # 3. Steam (default library only; other libraries: pass -Blender)
    $steam = (Get-ItemProperty "HKCU:\Software\Valve\Steam" -ErrorAction SilentlyContinue).SteamPath
    if ($steam) {
        $exe = Join-Path $steam "steamapps\common\Blender\blender.exe"
        if (Test-Path -LiteralPath $exe) { $found[$exe.ToLower()] = @{ Exe = $exe; Source = "steam" } }
    }
    # 4. Microsoft Store: listed but WindowsApps folders can't be run directly from scripts -> install from inside Blender
    foreach ($pkg in (Get-AppxPackage -Name "*Blender*" -ErrorAction SilentlyContinue)) {
        $exe = Join-Path $pkg.InstallLocation "Blender\blender.exe"
        $found[$exe.ToLower()] = @{ Exe = $exe; Source = "store" }
    }
    $result = @()
    foreach ($item in $found.Values) {
        $v = Get-VersionFromPath $item.Exe
        $ok = ($null -ne $v) -and ($v -ge $script:MinVersion) -and ($v -lt $script:MaxVersion) -and ($item.Source -ne "store")
        $result += [pscustomobject]@{ Exe = $item.Exe; Version = "$v"; Source = $item.Source; Compatible = $ok }
    }
    return $result | Sort-Object Version -Descending
}

function Test-BlenderRunning([string]$Exe) {
    $full = (Resolve-Path -LiteralPath $Exe).Path
    $running = Get-Process -Name blender -ErrorAction SilentlyContinue | Where-Object {
        try { $_.Path -and ((Resolve-Path -LiteralPath $_.Path).Path -eq $full) } catch { $false }
    }
    return [bool]$running
}

function Invoke-Blender([string]$Exe, [string[]]$Arguments) {
    # stdin from NUL: `blender --command` waits on an interactive stdin
    $out = & cmd.exe /c "`"$Exe`" $($Arguments -join ' ') < NUL 2>&1"
    return @{ Code = $LASTEXITCODE; Output = ($out -join "`n") }
}

function Invoke-Helper([string]$Exe, [string]$Mode) {
    $tmp = [System.IO.Path]::GetTempFileName()
    $r = Invoke-Blender $Exe @("-b", "--python", "`"$Helper`"", "--", $Mode, "`"$tmp`"")
    $data = $null
    if ((Get-Item -LiteralPath $tmp).Length -gt 0) { $data = Get-Content -LiteralPath $tmp -Raw | ConvertFrom-Json }
    Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue
    if (-not $data) { throw "Blender helper ($Mode) gave no result:`n$($r.Output)" }
    return $data
}

function Select-Targets {
    $given = @($Blender | ForEach-Object { $_ -split ";" } | Where-Object { $_ })
    if ($TargetsFile -and (Test-Path -LiteralPath $TargetsFile)) {
        $given += @(Get-Content -LiteralPath $TargetsFile | Where-Object { $_ -and (Test-Path -LiteralPath $_) })
    }
    if ($given.Count -gt 0) { return $given }
    if ($TargetsFile) { return @() }   # uninstall: nothing recorded (or Blender gone) = nothing to do
    $all = @(Find-Blender | Where-Object { $_.Compatible })
    if ($all.Count -eq 0) { Write-Error "No compatible Blender ($script:MinVersion - <$script:MaxVersion) found; pass -Blender <path to blender.exe>"; exit 2 }
    return @($all[0].Exe)   # newest; the Inno Setup page passes the user's choice with -Blender
}

if ($Zip) { Read-ManifestRange (Resolve-Path -LiteralPath $Zip).Path }

if ($List) {
    $items = Find-Blender
    if ($Json) { ConvertTo-Json @($items) -Compress }
    elseif ($Plain) { $items | ForEach-Object { "$($_.Exe)|$($_.Version)|$($_.Source)|$($_.Compatible)" } }
    else { $items | Format-Table -AutoSize | Out-String | Write-Output }
    exit 0
}

$status = 0
if ($Install) {
    if (-not $Zip) { Write-Error "-Install needs -Zip <maya-workflow-kit-x.y.z.zip>"; exit 1 }
    $zipPath = (Resolve-Path -LiteralPath $Zip).Path
    foreach ($exe in (Select-Targets)) {
        if (Test-BlenderRunning $exe) { Write-Output "Close Blender first: $exe"; $status = 3; continue }
        $r = Invoke-Blender $exe @("--command", "extension", "install-file", "-r", "user_default", "--enable", "`"$zipPath`"")
        if ($r.Code -ne 0) { Write-Output "Install failed for ${exe}:`n$($r.Output)"; $status = 1; continue }
        $s = Invoke-Helper $exe "status"
        if (-not $s.enabled) { Write-Output "Installed but not enabled for ${exe}: $($s.message)"; $status = 1; continue }
        Write-Output "Installed Maya Workflow Kit for Blender $($s.blender) (keymap: $($s.keyconfig))"
        if ($Record) { Add-Content -LiteralPath $Record -Value $exe -Encoding UTF8 }
        if ($MakeMaya) {
            $m = Invoke-Helper $exe "make"
            Write-Output $m.message
            if (-not $m.ok) { $status = 1 }
        }
    }
}
if ($Uninstall) {
    foreach ($exe in (Select-Targets)) {
        if (Test-BlenderRunning $exe) { Write-Output "Close Blender first: $exe"; $status = 3; continue }
        $r = Invoke-Helper $exe "remove"
        Write-Output "Blender $($r.blender): $($r.message)"
        if (-not $r.ok) { $status = 1 }
    }
}
exit $status
