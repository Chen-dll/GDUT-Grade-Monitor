param(
  [string]$DistDir = "dist"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $repoRoot
try {
  $targets = @(
    (Join-Path $DistDir "GDUTGradeMonitor-Setup.exe"),
    (Join-Path $DistDir "GDUTGradeMonitor-portable.zip")
  )
  $missing = $targets | Where-Object { -not (Test-Path -LiteralPath $_) }
  if ($missing.Count -gt 0) {
    throw "Cannot write SHA256SUMS.txt because release asset is missing: $($missing -join ', ')"
  }

  $optionalPatchAssets = Get-ChildItem -LiteralPath $DistDir -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "GDUTGradeMonitor-patch-v*-to-v*.*" -and ($_.Extension -in @(".zip", ".json")) } |
    Sort-Object Name

  $allTargets = @($targets) + @($optionalPatchAssets.FullName)

  $lines = foreach ($target in $allTargets) {
    $file = Get-Item -LiteralPath $target
    $hash = Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256
    "$($hash.Hash.ToLowerInvariant())  $($file.Name)"
  }

  $output = Join-Path $DistDir "SHA256SUMS.txt"
  $lines | Set-Content -LiteralPath $output -Encoding ascii
  Write-Host "Checksums written:" -ForegroundColor Green
  Write-Host (Resolve-Path $output)
}
finally {
  Pop-Location
}
