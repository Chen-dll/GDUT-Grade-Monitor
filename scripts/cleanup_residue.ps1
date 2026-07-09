param(
  [switch]$RemoveLocalData,
  [switch]$NoPrompt,
  [switch]$DryRun
)

$ErrorActionPreference = "Continue"

Write-Host "GDUTGradeMonitor-Cleanup.ps1" -ForegroundColor Cyan
Write-Host "Clean leftover startup entries after the portable folder was deleted." -ForegroundColor Cyan
Write-Host ""

$startupFile = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\GDUT Grade Monitor.vbs"
$dataDir = Join-Path $env:USERPROFILE ".gdut-grade-monitor"
$runKeyPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$runKeyName = "GDUT Grade Monitor"

if (Test-Path -LiteralPath $startupFile) {
  if ($DryRun) {
    Write-Host "Dry run: would remove startup file: $startupFile" -ForegroundColor Yellow
  } else {
    Remove-Item -LiteralPath $startupFile -Force
    Write-Host "Removed startup file: $startupFile" -ForegroundColor Green
  }
} else {
  Write-Host "Startup file not found: $startupFile" -ForegroundColor DarkGray
}

try {
  $runValue = Get-ItemProperty -Path $runKeyPath -Name $runKeyName -ErrorAction Stop
  if ($null -ne $runValue) {
    if ($DryRun) {
      Write-Host "Dry run: would remove registry startup item: $runKeyName" -ForegroundColor Yellow
    } else {
      Remove-ItemProperty -Path $runKeyPath -Name $runKeyName -Force
      Write-Host "Removed registry startup item: $runKeyName" -ForegroundColor Green
    }
  }
} catch {
  Write-Host "Registry startup item not found: $runKeyName" -ForegroundColor DarkGray
}

if ($DryRun) {
  Write-Host "Dry run: would delete scheduled task: GDUT Grade Monitor" -ForegroundColor Yellow
} else {
  $taskOutput = & schtasks /Delete /TN "GDUT Grade Monitor" /F 2>&1
  if ($LASTEXITCODE -eq 0) {
    Write-Host "Removed scheduled task: GDUT Grade Monitor" -ForegroundColor Green
  } else {
    Write-Host "Scheduled task not found, or removal failed." -ForegroundColor DarkGray
    if ($taskOutput) {
      Write-Host ($taskOutput -join "`n") -ForegroundColor DarkGray
    }
  }
}

if (-not $RemoveLocalData -and -not $NoPrompt) {
  Write-Host ""
  $answer = Read-Host "Also delete local config, cookies, grade snapshot, and logs? Type y to delete"
  $RemoveLocalData = $answer -in @("y", "Y", "yes", "YES")
}

if ($RemoveLocalData) {
  if (Test-Path -LiteralPath $dataDir) {
    if ($DryRun) {
      Write-Host "Dry run: would remove local data directory: $dataDir" -ForegroundColor Yellow
    } else {
      Remove-Item -LiteralPath $dataDir -Recurse -Force
      Write-Host "Removed local data directory: $dataDir" -ForegroundColor Green
    }
  } else {
    Write-Host "Local data directory not found: $dataDir" -ForegroundColor DarkGray
  }
} else {
  Write-Host "Kept local data directory: $dataDir" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Note: this cleanup tool does not delete passwords or notification secrets from Windows Credential Manager." -ForegroundColor Yellow
Write-Host "To remove them, open Windows Credential Manager and delete gdut-grade-monitor credentials." -ForegroundColor Yellow

if (-not $NoPrompt) {
  Write-Host ""
  Read-Host "Cleanup finished. Press Enter to exit"
}
