param(
  [switch]$SkipExeBuild
)

$ErrorActionPreference = "Stop"

function Find-InnoSetupCompiler {
  if ($env:INNO_SETUP_ISCC -and (Test-Path -LiteralPath $env:INNO_SETUP_ISCC)) {
    return $env:INNO_SETUP_ISCC
  }

  $command = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
  if ($command) {
    return $command.Source
  }

  $registryPaths = @(
    "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
    "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
    "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*"
  )

  $install = Get-ItemProperty $registryPaths -ErrorAction SilentlyContinue |
    Where-Object { $_.DisplayName -like "Inno Setup*" -and $_.InstallLocation } |
    Select-Object -First 1
  if ($install) {
    $candidate = Join-Path $install.InstallLocation "ISCC.exe"
    if (Test-Path -LiteralPath $candidate) {
      return $candidate
    }
  }

  $candidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 5\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 5\ISCC.exe"
  )

  foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path -LiteralPath $candidate)) {
      return $candidate
    }
  }

  throw "Inno Setup compiler ISCC.exe was not found. Install Inno Setup from https://jrsoftware.org/isinfo.php or set INNO_SETUP_ISCC to ISCC.exe."
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $repoRoot
try {
  if (-not $SkipExeBuild) {
    Write-Host "Building app folder first..." -ForegroundColor Cyan
    powershell -ExecutionPolicy Bypass -File "scripts\build_exe.ps1"
  }

  if (-not (Test-Path -LiteralPath "dist\GDUTGradeMonitor\GDUTGradeMonitor.exe")) {
    throw "dist\GDUTGradeMonitor\GDUTGradeMonitor.exe was not found. Run scripts\build_exe.ps1 first."
  }

  $iscc = Find-InnoSetupCompiler
  Write-Host "Building installer with Inno Setup..." -ForegroundColor Cyan
  & $iscc "packaging\installer\GDUTGradeMonitor.iss"

  if (-not (Test-Path -LiteralPath "dist\GDUTGradeMonitor-Setup.exe")) {
    throw "Installer build finished but dist\GDUTGradeMonitor-Setup.exe was not found."
  }

  Write-Host ""
  Write-Host "Installer build complete:" -ForegroundColor Green
  Write-Host (Resolve-Path "dist\GDUTGradeMonitor-Setup.exe")
}
finally {
  Pop-Location
}
