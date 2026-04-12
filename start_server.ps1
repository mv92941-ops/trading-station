# 交易工作站啟動腳本
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location "$root\backend"

Write-Host "=============================" -ForegroundColor Cyan
Write-Host "  交易工作站 啟動中..." -ForegroundColor Cyan
Write-Host "=============================" -ForegroundColor Cyan

# 背景啟動伺服器
$proc = Start-Process -FilePath "python" `
    -ArgumentList "-m", "uvicorn", "main:app", "--host", "localhost", "--port", "8000" `
    -PassThru -NoNewWindow

Write-Host "等待伺服器就緒 (3秒)..." -ForegroundColor Yellow
Start-Sleep -Seconds 3

Write-Host "開啟瀏覽器..." -ForegroundColor Green
Start-Process "http://localhost:8000"

Write-Host ""
Write-Host "伺服器運行中 -> http://localhost:8000" -ForegroundColor Cyan
Write-Host "關閉此視窗即停止伺服器" -ForegroundColor Yellow
Write-Host "=============================" -ForegroundColor Cyan

$proc.WaitForExit()
