$ErrorActionPreference = "Stop"

Write-Host "Installing build dependency..." -ForegroundColor Cyan
python -m pip install ".[build]"

$staleOneFile = ".\dist\GDUTGradeMonitor.exe"
if (Test-Path -LiteralPath $staleOneFile) {
  Remove-Item -LiteralPath $staleOneFile -Force
}

Write-Host "Building GDUTGradeMonitor app folder..." -ForegroundColor Cyan
python -m PyInstaller `
  --noconfirm `
  --clean `
  --onedir `
  --windowed `
  --name GDUTGradeMonitor `
  --icon gdut_grade_monitor\assets\icon.ico `
  --add-data "gdut_grade_monitor\assets\icon.ico;gdut_grade_monitor\assets" `
  --hidden-import keyring.backends.Windows `
  --hidden-import win32timezone `
  --hidden-import PySide6.QtCore `
  --hidden-import PySide6.QtGui `
  --hidden-import PySide6.QtPrintSupport `
  --hidden-import PySide6.QtWidgets `
  --hidden-import winotify `
  --exclude-module keyring.backends.SecretService `
  --exclude-module keyring.backends.chainer `
  --exclude-module keyring.backends.kwallet `
  --exclude-module keyring.backends.libsecret `
  --exclude-module keyring.backends.macOS `
  --exclude-module PySide6.QtOpenGL `
  --exclude-module PySide6.QtPdf `
  --exclude-module PySide6.QtQml `
  --exclude-module PySide6.QtQuick `
  --exclude-module PySide6.QtSvg `
  --exclude-module PySide6.QtVirtualKeyboard `
  packaging\desktop_launcher.py

Write-Host "Pruning unused packaged modules..." -ForegroundColor Cyan
$internalDir = ".\dist\GDUTGradeMonitor\_internal"
$pysideDir = Join-Path $internalDir "PySide6"

$unusedPaths = @(
  (Join-Path $pysideDir "Qt6Quick.dll"),
  (Join-Path $pysideDir "Qt6Qml.dll"),
  (Join-Path $pysideDir "Qt6QmlModels.dll"),
  (Join-Path $pysideDir "Qt6QmlMeta.dll"),
  (Join-Path $pysideDir "Qt6QmlWorkerScript.dll"),
  (Join-Path $pysideDir "Qt6Pdf.dll"),
  (Join-Path $pysideDir "Qt6VirtualKeyboard.dll"),
  (Join-Path $pysideDir "Qt6Svg.dll"),
  (Join-Path $pysideDir "Qt6OpenGL.dll"),
  (Join-Path $pysideDir "QtNetwork.pyd"),
  (Join-Path $pysideDir "Qt6Network.dll"),
  (Join-Path $internalDir "cryptography"),
  (Join-Path $internalDir "cryptography-48.0.0.dist-info"),
  (Join-Path $internalDir "_cffi_backend.cp314-win_amd64.pyd"),
  (Join-Path $internalDir "libcrypto-3-x64.dll"),
  (Join-Path $internalDir "libssl-3-x64.dll")
)
foreach ($path in $unusedPaths) {
  if (Test-Path -LiteralPath $path) {
    Remove-Item -LiteralPath $path -Recurse -Force
  }
}

$translationsDir = Join-Path $pysideDir "translations"
if (Test-Path -LiteralPath $translationsDir) {
  Get-ChildItem -LiteralPath $translationsDir -File |
    Where-Object { $_.Name -notin @("qt_zh_CN.qm", "qtbase_zh_CN.qm") } |
    Remove-Item -Force
}

Copy-Item -LiteralPath "README.md" -Destination ".\dist\GDUTGradeMonitor\README.md" -Force
Copy-Item -LiteralPath "PRIVACY.md" -Destination ".\dist\GDUTGradeMonitor\PRIVACY.md" -Force
Copy-Item -LiteralPath "LICENSE" -Destination ".\dist\GDUTGradeMonitor\LICENSE" -Force

$zipPath = ".\dist\GDUTGradeMonitor-portable.zip"
if (Test-Path -LiteralPath $zipPath) {
  Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -Path ".\dist\GDUTGradeMonitor" -DestinationPath $zipPath

Write-Host ""
Write-Host "Build complete:" -ForegroundColor Green
Write-Host (Resolve-Path ".\dist\GDUTGradeMonitor\GDUTGradeMonitor.exe")
Write-Host (Resolve-Path $zipPath)
