# Launches the full 4-service Market Intelligence MCP stack locally on Windows:
#   1. FastAPI Internal Market Backend   -> http://127.0.0.1:8000
#   2. Market Intelligence MCP Gateway   -> http://127.0.0.1:8080/mcp
#   3. FastAPI AI Orchestrator           -> http://127.0.0.1:8001
#   4. Next.js Market Intelligence UI    -> http://127.0.0.1:3000

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

$procs = @()
try {
    Write-Host "[1/4] Starting FastAPI Market Backend on :8000..." -ForegroundColor Cyan
    $procs += Start-Process -FilePath "$Root\market-backend\.venv\Scripts\python.exe" `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
        -WorkingDirectory "$Root\market-backend" -PassThru

    Write-Host "[2/4] Starting Market Intelligence MCP Server on :8080..." -ForegroundColor Cyan
    $procs += Start-Process -FilePath "$Root\market-intelligence-mcp\.venv\Scripts\python.exe" `
        -ArgumentList "-m", "app.main", "--transport", "streamable-http", "--host", "127.0.0.1", "--port", "8080" `
        -WorkingDirectory "$Root\market-intelligence-mcp" -PassThru

    Write-Host "[3/4] Starting FastAPI AI Orchestrator on :8001..." -ForegroundColor Cyan
    $procs += Start-Process -FilePath "$Root\ai-orchestrator\.venv\Scripts\python.exe" `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001" `
        -WorkingDirectory "$Root\ai-orchestrator" -PassThru

    Write-Host "[4/4] Starting Next.js Frontend on :3000..." -ForegroundColor Cyan
    $procs += Start-Process -FilePath "npm.cmd" `
        -ArgumentList "run", "dev" `
        -WorkingDirectory "$Root\frontend" -PassThru

    Write-Host ""
    Write-Host "Full stack running! Open http://127.0.0.1:3000 in your browser." -ForegroundColor Green
    Write-Host "Press Ctrl+C to stop all services." -ForegroundColor Yellow

    while ($true) { Start-Sleep -Seconds 2 }
}
finally {
    Write-Host "Stopping services..." -ForegroundColor Yellow
    foreach ($p in $procs) {
        if ($p -and -not $p.HasExited) {
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        }
    }
}
