$ErrorActionPreference = "Stop"

Write-Host "Installing GDUT Grade Monitor..." -ForegroundColor Cyan
python -m pip install -e .

Write-Host ""
Write-Host "Running environment check..." -ForegroundColor Cyan
python -m gdut_grade_monitor doctor

Write-Host ""
Write-Host "Opening the desktop app. Click '一键配置本机' to finish setup." -ForegroundColor Green
python -m gdut_grade_monitor gui
