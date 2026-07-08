$ErrorActionPreference = "Stop"

Write-Host "Removing GDUT Grade Monitor autostart..." -ForegroundColor Cyan
python -m gdut_grade_monitor task uninstall

Write-Host ""
Write-Host "Package files are not removed automatically because this project is installed editable from its folder." -ForegroundColor Yellow
Write-Host "To remove the Python package entry, run:"
Write-Host "python -m pip uninstall gdut-grade-monitor"
