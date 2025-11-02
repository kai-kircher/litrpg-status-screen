# PowerShell script to create .env.production with a secure password

Write-Host "🔒 Creating .env.production file..." -ForegroundColor Cyan

# Check if .env.production already exists
if (Test-Path ".env.production") {
    Write-Host "⚠️  .env.production already exists!" -ForegroundColor Yellow
    $response = Read-Host "Do you want to overwrite it? (y/N)"
    if ($response -ne 'y' -and $response -ne 'Y') {
        Write-Host "❌ Aborted. Keeping existing .env.production" -ForegroundColor Red
        exit 1
    }
}

# Generate secure password
$SECURE_PASSWORD = -join ((65..90) + (97..122) + (48..57) + @(33,64,35,36,37,94,38,42) | Get-Random -Count 32 | ForEach-Object {[char]$_})

# Alternative: Use OpenSSL if available
if (Get-Command openssl -ErrorAction SilentlyContinue) {
    $SECURE_PASSWORD = & openssl rand -base64 32
}

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

# Create .env.production
$envContent = @"
# Production Environment Variables
# Generated on $timestamp

# Database Configuration
DB_HOST=postgres
DB_PORT=5432
DB_NAME=wandering_inn_tracker
DB_USER=wandering_inn
DB_PASSWORD=$SECURE_PASSWORD

# Node Environment
NODE_ENV=production

# Application Port (default: 3000)
PORT=3000
"@

$envContent | Out-File -FilePath ".env.production" -Encoding UTF8

Write-Host "✅ Created .env.production with secure password" -ForegroundColor Green
Write-Host ""
Write-Host "📝 Database password: $SECURE_PASSWORD" -ForegroundColor White
Write-Host ""
Write-Host "⚠️  IMPORTANT: Save this password securely!" -ForegroundColor Yellow
Write-Host "   You'll need it if you want to access the database directly." -ForegroundColor Yellow
Write-Host ""
Write-Host "🚀 You can now run: .\deploy.ps1" -ForegroundColor Green
