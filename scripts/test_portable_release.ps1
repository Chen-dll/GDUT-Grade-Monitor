param(
  [string]$ZipPath = ".\dist\GDUTGradeMonitor-portable.zip",
  [switch]$SkipLaunch
)

# Usage: powershell -ExecutionPolicy Bypass -File scripts\test_portable_release.ps1 -SkipLaunch
$ErrorActionPreference = "Stop"

function Assert-Exists($Path, $Message) {
  if (-not (Test-Path -LiteralPath $Path)) {
    throw $Message
  }
}

function Remove-SmokeDirectory($Path) {
  if (-not (Test-Path -LiteralPath $Path)) {
    return
  }

  $resolved = (Resolve-Path -LiteralPath $Path).Path
  $tempRoot = [System.IO.Path]::GetTempPath()
  if (-not $resolved.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to delete smoke test directory outside temp: $resolved"
  }

  [System.GC]::Collect()
  [System.GC]::WaitForPendingFinalizers()
  [System.IO.Directory]::Delete($resolved, $true)
}

function Test-PortableCase($CaseName, $Destination, $ZipPath, $SkipLaunch) {
  Write-Host "Testing portable case: $CaseName" -ForegroundColor Cyan
  if (Test-Path -LiteralPath $Destination) {
    Remove-SmokeDirectory $Destination
  }
  New-Item -ItemType Directory -Path $Destination -Force | Out-Null
  Expand-Archive -LiteralPath $ZipPath -DestinationPath $Destination -Force

  $appDir = Join-Path $Destination "GDUTGradeMonitor"
  $exe = Join-Path $appDir "GDUTGradeMonitor.exe"
  $cleanupCmd = Join-Path $appDir "GDUTGradeMonitor-Cleanup.cmd"
  $cleanupPs1 = Join-Path $appDir "GDUTGradeMonitor-Cleanup.ps1"
  $readme = Join-Path $appDir "README.md"
  $privacy = Join-Path $appDir "PRIVACY.md"

  Assert-Exists $exe "Missing GDUTGradeMonitor.exe in $CaseName"
  Assert-Exists $cleanupCmd "Missing GDUTGradeMonitor-Cleanup.cmd in $CaseName"
  Assert-Exists $cleanupPs1 "Missing GDUTGradeMonitor-Cleanup.ps1 in $CaseName"
  Assert-Exists $readme "Missing README.md in $CaseName"
  Assert-Exists $privacy "Missing PRIVACY.md in $CaseName"

  if (-not $SkipLaunch) {
    $process = Start-Process -FilePath $exe -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 8
    $alive = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
    if (-not $alive) {
      throw "GDUTGradeMonitor.exe exited too early in $CaseName"
    }
    Stop-Process -Id $process.Id -Force
    Start-Sleep -Seconds 1
  }
}

$resolvedZip = Resolve-Path -LiteralPath $ZipPath
$root = Join-Path ([System.IO.Path]::GetTempPath()) ("GDUTGradeMonitorPortableSmoke-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $root -Force | Out-Null

try {
  Test-PortableCase "normal path" (Join-Path $root "NormalPath") $resolvedZip $SkipLaunch
  Test-PortableCase "中文路径" (Join-Path $root "中文路径") $resolvedZip $SkipLaunch
  Test-PortableCase "Path With Spaces" (Join-Path $root "Path With Spaces") $resolvedZip $SkipLaunch
  Write-Host "Portable release smoke tests passed." -ForegroundColor Green
}
finally {
  if (Test-Path -LiteralPath $root) {
    Remove-SmokeDirectory $root
  }
}
