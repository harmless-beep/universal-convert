# =====================================================================
# Universal Convert - Windows installer
# =====================================================================
# Registers the "Convert With..." right-click menu entry for the current
# user (HKCU - no admin rights needed).
#
#   install (Python):    powershell -ExecutionPolicy Bypass -File installers\windows.ps1
#   install (the exe):   powershell -ExecutionPolicy Bypass -File installers\windows.ps1 -ExePath .\Universal-Convert-0.1.0-windows.exe
#   also LibreOffice:    ... -InstallLibreOffice
#   don't check for it:  ... -SkipLibreOffice
#   uninstall:           ... -Uninstall
#
# Run it from wherever the repository (or the downloaded exe) is.
#
# Python mode builds a .venv inside the project folder and points the menu
# at that, so the app's packages never touch your system Python - and a
# machine without Pillow installed yet still works, because Pillow is
# installed into the venv by this script.
# =====================================================================

[CmdletBinding()]
param(
    [switch]$Uninstall,
    [switch]$SkipLibreOffice,
    [switch]$InstallLibreOffice,
    [string]$ExePath
)

$ErrorActionPreference = 'Stop'

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path | Split-Path -Parent
$MainPy     = Join-Path $ProjectDir 'main.py'
$Reqs       = Join-Path $ProjectDir 'requirements.txt'
$MenuTitle  = 'Convert With...'
$RegKey     = 'HKCU:\Software\Classes\*\shell\ConvertWith'
# (used ONLY via -LiteralPath - see the registry section below)
$RegSub     = 'Software\Classes\*\shell\ConvertWith'
$RegSubCmd  = "$RegSub\command"

$VenvDir    = Join-Path $ProjectDir '.venv'
$VenvPy     = Join-Path $VenvDir 'Scripts\python.exe'
$VenvPyw    = Join-Path $VenvDir 'Scripts\pythonw.exe'

$ExeInstallDir = Join-Path $env:LOCALAPPDATA 'Programs\UniversalConvert'
$ExeInstall    = Join-Path $ExeInstallDir 'UniversalConvert.exe'

function Info($m) { Write-Host $m -ForegroundColor Cyan }
function OK($m)   { Write-Host "  [OK] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  [!!] $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "  [XX] $m" -ForegroundColor Red; exit 1 }

# PowerShell 5.1 turns native-command stderr into a terminating error when
# $ErrorActionPreference='Stop'. Every native call must go through this.
function Invoke-Native([scriptblock]$Block) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Block; return $LASTEXITCODE } finally { $ErrorActionPreference = $prev }
}

# NOTE: the key path contains a literal '*' which PowerShell's *-Item cmdlets
# treat as a WILDCARD (-Path would expand it to every registered file class),
# and PS 5.1's New-Item has no -LiteralPath. So key creation goes through the
# .NET Registry API (purely literal) and values through -LiteralPath.
function New-RegKey([string]$subPath) {
    return [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($subPath)
}

function Register-Menu([string]$launcher, [string]$prefix) {
    Info "Adding the '$MenuTitle' context menu entry (current user only)..."
    New-RegKey $RegSub   | Out-Null
    New-RegKey $RegSubCmd | Out-Null

    # MultiSelectModel=Document lets Explorer offer the menu for selections up
    # to 100 files; %1 is the clicked file and sibling instances are merged by
    # main.py's aggregator. No console window: pythonw / the exe itself.
    $cmd = '{0} "%1"' -f $prefix

    Set-ItemProperty -LiteralPath $RegKey -Name '(Default)'      -Value $MenuTitle
    Set-ItemProperty -LiteralPath $RegKey -Name 'MUIVerb'        -Value $MenuTitle
    Set-ItemProperty -LiteralPath $RegKey -Name 'MultiSelectModel' -Value 'Document'
    Set-ItemProperty -LiteralPath $RegKey -Name 'Icon'           -Value "$launcher,0"
    Set-ItemProperty -LiteralPath $RegKey -Name 'NeverDefault'   -Value '' -Type String
    Set-ItemProperty -LiteralPath "$RegKey\command" -Name '(Default)' -Value $cmd

    $k = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($RegSubCmd)
    $check = if ($k) { $k.GetValue('') } else { $null }
    if ($k) { $k.Close() }
    if ($check -ne $cmd) { Fail "Verification failed - registry value mismatch." }
    OK "Registry entries written and verified."
}

function Install-LibreOffice {
    Info "Checking LibreOffice..."
    $loPaths = @(
        (Join-Path $env:ProgramFiles 'LibreOffice\program\soffice.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'LibreOffice\program\soffice.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\LibreOffice\program\soffice.exe')
    )
    $lo = $loPaths | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    if (-not $lo) {
        $cmd = Get-Command soffice -ErrorAction SilentlyContinue
        if ($cmd) { $lo = $cmd.Source }
    }
    if ($lo) { OK "LibreOffice: $lo"; return }

    if (-not $InstallLibreOffice) {
        Warn "LibreOffice not found - Office -> PDF conversions need it."
        Warn "  Install it later from libreoffice.org, or re-run with -InstallLibreOffice."
        return
    }
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Warn "winget is not available - install LibreOffice from libreoffice.org instead."
        return
    }
    Info "Running: winget install TheDocumentFoundation.LibreOffice"
    $rc = Invoke-Native {
        winget install --id TheDocumentFoundation.LibreOffice -e `
            --accept-source-agreements --accept-package-agreements --silent
    }
    if ($rc -eq 0) { OK "LibreOffice installed." }
    else { Warn "winget exited with $rc - install LibreOffice manually if you need it." }
}

# ---------------------------------------------------------------- uninstall
if ($Uninstall) {
    Info "Removing the '$MenuTitle' context menu entry..."
    if (Test-Path -LiteralPath $RegKey) {
        Remove-Item -LiteralPath $RegKey -Recurse -Force
        OK "Removed $RegKey"
    } else {
        Warn "Entry not found (already uninstalled?)"
    }
    if (Test-Path -LiteralPath $ExeInstallDir) {
        Remove-Item -LiteralPath $ExeInstallDir -Recurse -Force
        OK "Removed $ExeInstallDir"
    }
    if (Test-Path -LiteralPath $VenvDir) {
        Info "Kept $VenvDir (delete it by hand if you want the space back)."
    }
    Info "Done."
    exit 0
}

Write-Host ""
Info "Universal Convert installer"
Write-Host "Project: $ProjectDir"

# -------------------------------------------------------- exe mode (no Python)
if ($ExePath) {
    if (-not (Test-Path -LiteralPath $ExePath)) { Fail "Exe not found: $ExePath" }
    $src = (Resolve-Path -LiteralPath $ExePath).Path
    Info "Installing the app to $ExeInstallDir ..."
    New-Item -ItemType Directory -Force -Path $ExeInstallDir | Out-Null
    if ($src -ne $ExeInstall) {
        try { Copy-Item -LiteralPath $src -Destination $ExeInstall -Force }
        catch { Fail "Could not copy the exe: $($_.Exception.Message)" }
    }
    OK "App: $ExeInstall"
    Register-Menu $ExeInstall ('"{0}"' -f $ExeInstall)
    if (-not $SkipLibreOffice) { Install-LibreOffice }
    Write-Host ""
    Write-Host "Install complete (no Python involved)." -ForegroundColor Green
    Write-Host "Right-click any image/PDF/Office file in Explorer and choose"
    Write-Host "'$MenuTitle'. On Windows 11, look under 'Show more options'."
    exit 0
}

# ------------------------------------------------------------ 1. find Python
if (-not (Test-Path -LiteralPath $MainPy)) {
    Fail "main.py not found at $MainPy - run this from the project folder."
}
# We don't just take the first Python on PATH - we take the first one that can
# actually run the app (3.9+, tkinter, venv). Pillow is NOT checked here: it
# is installed into .venv below, so a bare Python is good enough.
Info "Looking for a Python 3 (3.9+, tkinter, venv)..."
$candidates = @()
$pyCmd = Get-Command python -ErrorAction SilentlyContinue
if ($pyCmd) { $candidates += $pyCmd.Source }
$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($pyLauncher) {
    $p = Invoke-Native { & py -3 -c "import sys; print(sys.executable)" 2>$null }
    if ($p -and (Test-Path -LiteralPath "$p")) { $candidates += "$p" }
}
$candidates += (Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe",
                                        "$env:LOCALAPPDATA\Microsoft\WindowsApps\python*.exe",
                                        'C:\Python3*\python.exe' -ErrorAction SilentlyContinue).FullName

$pyExe = $null
$tried = @()
foreach ($cand in ($candidates | Select-Object -Unique)) {
    if (-not $cand -or -not (Test-Path -LiteralPath $cand)) { continue }
    $tried += $cand
    $out = Invoke-Native { & $cand -c "import sys, tkinter, venv; assert sys.version_info >= (3, 9); print('UC_OK')" 2>$null }
    if ($out -contains 'UC_OK') { $pyExe = $cand; break }
}
if (-not $pyExe) {
    $msg = "No usable Python was found. Tried: $($tried -join ', ')" + [Environment]::NewLine +
           "Install Python 3.9+ from https://www.python.org/downloads/ (tick 'Add python.exe to PATH')," + [Environment]::NewLine +
           "then re-run this installer. Nothing else is needed - it installs the packages itself."
    Fail $msg
}
OK "Python: $pyExe"

# ------------------------------------------------------- 2. project venv
# Always rebuilt: idempotent, and a half-broken venv from an earlier run can
# never leak into a working install.
Info "Creating $VenvDir ..."
Remove-Item -LiteralPath $VenvDir -Recurse -Force -ErrorAction SilentlyContinue
$rc = Invoke-Native { & $pyExe -m venv $VenvDir }
if ($rc -ne 0 -or -not (Test-Path -LiteralPath $VenvPy)) {
    Fail "python -m venv failed. The Microsoft Store Python build often cannot do this -" + [Environment]::NewLine +
         "install Python from python.org instead and re-run."
}
OK "Virtual environment created"

Info "Installing Pillow, pypdf, PyMuPDF into .venv ..."
$reqArgs = if (Test-Path -LiteralPath $Reqs) { @('-r', $Reqs) } else { @('Pillow', 'pypdf', 'PyMuPDF') }
$rc = Invoke-Native { & $VenvPy -m pip install --quiet --disable-pip-version-check @reqArgs }
if ($rc -ne 0) {
    Warn "pip reported a problem (exit $rc) - verifying anyway, the packages may already be present."
}

$verified = Invoke-Native { & $VenvPy -c "import tkinter, PIL, pypdf, fitz; print('UC_OK')" 2>$null }
if ($verified -notcontains 'UC_OK') {
    Fail "The environment is still missing packages after install." + [Environment]::NewLine +
         "Try:  & '$VenvPy' -m pip install Pillow pypdf PyMuPDF" + [Environment]::NewLine +
         "then re-run this installer."
}
OK "Dependencies ready (Pillow, pypdf, PyMuPDF)"

# -------------------------------------------------------- 3. LibreOffice
if ($SkipLibreOffice) {
    Warn "Skipping LibreOffice check (-SkipLibreOffice)."
} else {
    Install-LibreOffice
}

# ------------------------------------------------------- 4. registry entry
$launcher = if (Test-Path -LiteralPath $VenvPyw) { $VenvPyw } else { $VenvPy }
Register-Menu $launcher ('"{0}" "{1}"' -f $launcher, $MainPy)

Write-Host ""
Write-Host "Install complete." -ForegroundColor Green
Write-Host "Right-click any image/PDF/Office file in Explorer and choose"
Write-Host "'$MenuTitle'. On Windows 11, look under 'Show more options'."
