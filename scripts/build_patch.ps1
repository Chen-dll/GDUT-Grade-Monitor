param(
  [Parameter(Mandatory = $true)][string]$OldVersion,
  [Parameter(Mandatory = $true)][string]$NewVersion,
  [Parameter(Mandatory = $true)][string]$PreviousDist,
  [Parameter(Mandatory = $true)][string]$CurrentDist,
  [string]$OutputDir = ".\dist"
)

$ErrorActionPreference = "Stop"

function Normalize-Version([string]$Version) {
  if ($Version.StartsWith("v")) {
    return $Version.Substring(1)
  }
  return $Version
}

function Get-RelativePath([string]$Base, [string]$Path) {
  $baseResolved = (Resolve-Path -LiteralPath $Base).Path
  $pathResolved = (Resolve-Path -LiteralPath $Path).Path
  $baseUri = [Uri]($baseResolved.TrimEnd("\") + "\")
  $pathUri = [Uri]$pathResolved
  return [Uri]::UnescapeDataString($baseUri.MakeRelativeUri($pathUri).ToString()).Replace("/", "\")
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

$OldVersion = Normalize-Version $OldVersion
$NewVersion = Normalize-Version $NewVersion
$previousRoot = (Resolve-Path -LiteralPath $PreviousDist).Path
$currentRoot = (Resolve-Path -LiteralPath $CurrentDist).Path
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$changedFiles = New-Object System.Collections.Generic.List[string]
Get-ChildItem -LiteralPath $currentRoot -Recurse -File | ForEach-Object {
  $relative = Get-RelativePath $currentRoot $_.FullName
  if (-not (Test-SafeRelativePath $relative)) {
    throw "Unsafe relative path: $relative"
  }
  $oldFile = Join-Path $previousRoot $relative
  $changed = $true
  if (Test-Path -LiteralPath $oldFile) {
    $oldHash = (Get-FileHash -LiteralPath $oldFile -Algorithm SHA256).Hash
    $newHash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
    $changed = $oldHash -ne $newHash
  }
  if ($changed) {
    $changedFiles.Add($relative)
  }
}

if ($changedFiles.Count -eq 0) {
  throw "No changed files detected; patch package was not created."
}

$assetPrefix = "GDUTGradeMonitor-patch-v$OldVersion-to-v$NewVersion"
$stage = Join-Path ([System.IO.Path]::GetTempPath()) ($assetPrefix + "-" + [Guid]::NewGuid().ToString("N"))
$payloadRoot = Join-Path $stage "GDUTGradeMonitor"
New-Item -ItemType Directory -Path $payloadRoot -Force | Out-Null

try {
  foreach ($relative in $changedFiles) {
    $source = Join-Path $currentRoot $relative
    $target = Join-Path $payloadRoot $relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $target -Force
  }

  $zipPath = Join-Path $OutputDir "$assetPrefix.zip"
  $manifestPath = Join-Path $OutputDir "$assetPrefix.json"
  if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
  }
  Compress-Archive -Path $payloadRoot -DestinationPath $zipPath -Force
  $archiveHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()

  $manifest = [ordered]@{
    schema = 1
    app = "GDUT Grade Monitor"
    from_version = "v$OldVersion"
    to_version = "v$NewVersion"
    archive = "$assetPrefix.zip"
    archive_sha256 = $archiveHash
    files = @($changedFiles | ForEach-Object { $_.Replace("\", "/") })
  }
  $manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

  Write-Host "Patch assets created:" -ForegroundColor Green
  Write-Host (Resolve-Path -LiteralPath $zipPath)
  Write-Host (Resolve-Path -LiteralPath $manifestPath)
} finally {
  Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
}
