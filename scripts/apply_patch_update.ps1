param(
  [Parameter(Mandatory = $true)][string]$ArchivePath,
  [Parameter(Mandatory = $true)][string]$ManifestPath,
  [Parameter(Mandatory = $true)][string]$InstallDir,
  [Parameter(Mandatory = $true)][int]$WaitPid,
  [Parameter(Mandatory = $true)][string]$ExecutablePath
)

$ErrorActionPreference = "Stop"

function Resolve-RequiredPath([string]$PathValue, [string]$Label) {
  if (-not (Test-Path -LiteralPath $PathValue)) {
    throw "$Label does not exist: $PathValue"
  }
  return (Resolve-Path -LiteralPath $PathValue).Path
}

function Test-SafeRelativePath([string]$RelativePath) {
  if ([string]::IsNullOrWhiteSpace($RelativePath)) {
    return $false
  }
  if ([System.IO.Path]::IsPathRooted($RelativePath)) {
    return $false
  }
  if ($RelativePath.Contains(":")) {
    return $false
  }
  $parts = $RelativePath -split "[/\\]+"
  return -not ($parts -contains "..")
}

$archive = Resolve-RequiredPath $ArchivePath "Patch archive"
$manifestFile = Resolve-RequiredPath $ManifestPath "Patch manifest"
$targetDir = Resolve-RequiredPath $InstallDir "Install directory"
$manifest = Get-Content -LiteralPath $manifestFile -Raw -Encoding UTF8 | ConvertFrom-Json

if ($manifest.schema -ne 1) {
  throw "Unsupported patch manifest schema."
}
if (-not $manifest.files -or $manifest.files.Count -eq 0) {
  throw "Patch manifest has no files."
}
foreach ($file in $manifest.files) {
  if (-not (Test-SafeRelativePath ([string]$file))) {
    throw "Patch manifest contains unsafe path: $file"
  }
}

try {
  $process = Get-Process -Id $WaitPid -ErrorAction SilentlyContinue
  if ($process) {
    Wait-Process -Id $WaitPid -Timeout 30 -ErrorAction SilentlyContinue
  }
} catch {
  Start-Sleep -Seconds 2
}

$stage = Join-Path ([System.IO.Path]::GetTempPath()) ("gdut-grade-monitor-patch-" + [Guid]::NewGuid().ToString("N"))
$backup = Join-Path ([System.IO.Path]::GetTempPath()) ("gdut-grade-monitor-backup-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $stage -Force | Out-Null
New-Item -ItemType Directory -Path $backup -Force | Out-Null

try {
  Expand-Archive -LiteralPath $archive -DestinationPath $stage -Force
  $payloadRoot = $stage
  $nested = Join-Path $stage "GDUTGradeMonitor"
  if (Test-Path -LiteralPath $nested) {
    $payloadRoot = $nested
  }

  foreach ($relative in $manifest.files) {
    $relativeText = [string]$relative
    $source = Join-Path $payloadRoot $relativeText
    $target = Join-Path $targetDir $relativeText
    $targetParent = Split-Path -Parent $target
    $backupTarget = Join-Path $backup $relativeText
    $backupParent = Split-Path -Parent $backupTarget

    if (-not (Test-Path -LiteralPath $source)) {
      throw "Patch archive is missing file: $relativeText"
    }
    if (Test-Path -LiteralPath $target) {
      New-Item -ItemType Directory -Path $backupParent -Force | Out-Null
      Copy-Item -LiteralPath $target -Destination $backupTarget -Force
    }
    New-Item -ItemType Directory -Path $targetParent -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $target -Force
  }

  if (Test-Path -LiteralPath $ExecutablePath) {
    Start-Process -FilePath $ExecutablePath -WindowStyle Normal
  }
} catch {
  foreach ($relative in $manifest.files) {
    $relativeText = [string]$relative
    $backupSource = Join-Path $backup $relativeText
    $target = Join-Path $targetDir $relativeText
    if (Test-Path -LiteralPath $backupSource) {
      Copy-Item -LiteralPath $backupSource -Destination $target -Force
    }
  }
  throw
} finally {
  Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $backup -Recurse -Force -ErrorAction SilentlyContinue
}
