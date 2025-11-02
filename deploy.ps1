# PowerShell Deployment Script for Wandering Inn Tracker

Write-Host "🚀 Deploying Wandering Inn Tracker..." -ForegroundColor Green

# Check if .env.production exists
if (-not (Test-Path ".env.production")) {
    Write-Host "❌ Error: .env.production file not found!" -ForegroundColor Red
    Write-Host "📝 Please create it from .env.production.example" -ForegroundColor Yellow
    exit 1
}

# Load environment variables from .env.production
Get-Content .env.production | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
        $name = $matches[1].Trim()
        $value = $matches[2].Trim()
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

Write-Host "📦 Building Docker images..." -ForegroundColor Cyan
docker compose -f docker-compose.prod.yml build

Write-Host "🗄️  Starting database..." -ForegroundColor Cyan
docker compose -f docker-compose.prod.yml up -d postgres

Write-Host "⏳ Waiting for database to be ready..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

Write-Host "🔄 Running database migrations..." -ForegroundColor Cyan
Push-Location database
if (Test-Path "migrate.ps1") {
    .\migrate.ps1
} else {
    Write-Host "⚠️  No migration script found, skipping..." -ForegroundColor Yellow
}
Pop-Location

Write-Host "🌐 Starting web application..." -ForegroundColor Cyan
docker compose -f docker-compose.prod.yml up -d web

Write-Host "✅ Deployment complete!" -ForegroundColor Green
Write-Host ""
Write-Host "📊 Application Status:" -ForegroundColor Cyan
docker compose -f docker-compose.prod.yml ps

$port = if ($env:PORT) { $env:PORT } else { "3000" }

Write-Host ""
Write-Host "🔗 Application should be accessible at:" -ForegroundColor Green
Write-Host "   http://localhost:$port" -ForegroundColor White
Write-Host ""
Write-Host "📝 To view logs:" -ForegroundColor Cyan
Write-Host "   docker compose -f docker-compose.prod.yml logs -f web" -ForegroundColor White
Write-Host ""
Write-Host "🛠️  To access admin panel:" -ForegroundColor Cyan
Write-Host "   http://localhost:$port/admin" -ForegroundColor White
