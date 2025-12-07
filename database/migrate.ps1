# Database migration runner for Windows PowerShell
# Usage: .\migrate.ps1 [up|status|reset]

param(
    [string]$Command = "up"
)

# Load environment variables if .env exists
if (Test-Path .env) {
    Get-Content .env | ForEach-Object {
        if ($_ -match '^([^=]+)=(.*)$') {
            Set-Item -Path "env:$($matches[1])" -Value $matches[2]
        }
    }
}

# Database connection parameters
$DB_HOST = if ($env:DB_HOST) { $env:DB_HOST } else { "localhost" }
$DB_PORT = if ($env:DB_PORT) { $env:DB_PORT } else { "5432" }
$DB_NAME = if ($env:DB_NAME) { $env:DB_NAME } else { "wandering_inn_tracker" }
$DB_USER = if ($env:DB_USER) { $env:DB_USER } else { "wandering_inn" }
$DB_PASSWORD = if ($env:DB_PASSWORD) { $env:DB_PASSWORD } else { "dev_password_change_in_production" }

# Set password environment variable
$env:PGPASSWORD = $DB_PASSWORD

# Migrations directory
$MIGRATIONS_DIR = Join-Path $PSScriptRoot "migrations"

# Function to run psql command
function Invoke-Psql {
    param(
        [string]$Query,
        [string]$File,
        [string]$Database = $DB_NAME
    )

    $args = @("-h", $DB_HOST, "-p", $DB_PORT, "-U", $DB_USER, "-d", $Database)

    if ($Query) {
        $args += @("-c", $Query)
    } elseif ($File) {
        $args += @("-f", $File)
    }

    & psql @args
}

# Function to check database connection, create if missing
function Test-DatabaseConnection {
    Write-Host "Checking database connection..." -ForegroundColor Cyan

    $result = Invoke-Psql -Database "postgres" -Query "SELECT 1 FROM pg_database WHERE datname='$DB_NAME';" 2>$null

    if (-not $result -or $result -notmatch "1") {
        Write-Host "Database '$DB_NAME' does not exist, creating..." -ForegroundColor Yellow
        try {
            Invoke-Psql -Database "postgres" -Query "CREATE DATABASE $DB_NAME;"
            Write-Host "Database '$DB_NAME' created successfully" -ForegroundColor Green
        } catch {
            Write-Host "Error: Failed to create database '$DB_NAME'" -ForegroundColor Red
            Write-Host $_.Exception.Message -ForegroundColor Red
            exit 1
        }
    }

    Write-Host "Database connection successful" -ForegroundColor Green
}

# Function to initialize migration tracking
function Initialize-Migrations {
    Write-Host "Initializing migration tracking..." -ForegroundColor Cyan
    $initFile = Join-Path $MIGRATIONS_DIR "000_create_migrations_table.sql"
    Invoke-Psql -File $initFile 2>$null | Out-Null
    Write-Host "Migration tracking initialized" -ForegroundColor Green
}

# Function to get applied migrations
function Get-AppliedMigrations {
    $query = "SELECT migration_name FROM schema_migrations ORDER BY migration_name;"
    $result = Invoke-Psql -Query $query -ErrorAction SilentlyContinue 2>$null
    return $result | Where-Object { $_.Trim() -ne "" }
}

# Function to get pending migrations
function Get-PendingMigrations {
    $applied = Get-AppliedMigrations
    $allMigrations = Get-ChildItem -Path $MIGRATIONS_DIR -Filter "*.sql" |
                     Where-Object { $_.Name -ne "000_create_migrations_table.sql" } |
                     Sort-Object Name

    $pending = @()
    foreach ($migration in $allMigrations) {
        if ($applied -notcontains $migration.Name) {
            $pending += $migration.Name
        }
    }

    return $pending
}

# Function to run migrations
function Start-Migration {
    Test-DatabaseConnection
    Initialize-Migrations

    $pending = Get-PendingMigrations

    if ($pending.Count -eq 0) {
        Write-Host "No pending migrations" -ForegroundColor Green
        return
    }

    Write-Host "Applying migrations..." -ForegroundColor Cyan

    foreach ($migration in $pending) {
        Write-Host "Applying: $migration" -ForegroundColor Yellow

        $migrationFile = Join-Path $MIGRATIONS_DIR $migration

        try {
            Invoke-Psql -File $migrationFile
            Invoke-Psql -Query "INSERT INTO schema_migrations (migration_name) VALUES ('$migration');"
            Write-Host "✓ Applied: $migration" -ForegroundColor Green
        } catch {
            Write-Host "✗ Failed: $migration" -ForegroundColor Red
            Write-Host $_.Exception.Message -ForegroundColor Red
            exit 1
        }
    }

    Write-Host "All migrations applied successfully" -ForegroundColor Green
}

# Function to show migration status
function Show-MigrationStatus {
    Test-DatabaseConnection
    Initialize-Migrations

    Write-Host ""
    Write-Host "=== Applied Migrations ===" -ForegroundColor Cyan
    $applied = Get-AppliedMigrations

    if ($applied.Count -eq 0) {
        Write-Host "None"
    } else {
        foreach ($migration in $applied) {
            Write-Host "✓ $migration" -ForegroundColor Green
        }
    }

    Write-Host ""
    Write-Host "=== Pending Migrations ===" -ForegroundColor Cyan
    $pending = Get-PendingMigrations

    if ($pending.Count -eq 0) {
        Write-Host "None"
    } else {
        foreach ($migration in $pending) {
            Write-Host "• $migration" -ForegroundColor Yellow
        }
    }
}

# Function to reset database
function Reset-Database {
    Write-Host "WARNING: This will drop and recreate the database!" -ForegroundColor Red
    $response = Read-Host "Are you sure? (yes/no)"

    if ($response -ne "yes") {
        Write-Host "Aborted"
        exit 0
    }

    Write-Host "Dropping database..." -ForegroundColor Yellow
    Invoke-Psql -Database "postgres" -Query "DROP DATABASE IF EXISTS $DB_NAME;" | Out-Null

    Write-Host "Creating database..." -ForegroundColor Yellow
    Invoke-Psql -Database "postgres" -Query "CREATE DATABASE $DB_NAME;" | Out-Null

    Write-Host "Running migrations..." -ForegroundColor Yellow
    Start-Migration

    Write-Host "Database reset complete" -ForegroundColor Green
}

# Main command handler
switch ($Command.ToLower()) {
    "up" {
        Start-Migration
    }
    "status" {
        Show-MigrationStatus
    }
    "reset" {
        Reset-Database
    }
    default {
        Write-Host "Usage: .\migrate.ps1 [up|status|reset]"
        Write-Host ""
        Write-Host "Commands:"
        Write-Host "  up      - Apply pending migrations (default)"
        Write-Host "  status  - Show migration status"
        Write-Host "  reset   - Drop and recreate database (DANGEROUS!)"
        exit 1
    }
}
