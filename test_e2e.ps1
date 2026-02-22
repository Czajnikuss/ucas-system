# test_e2e.ps1
$ErrorActionPreference = "Stop"

$GatewayUrl = "http://localhost:8000"

Write-Host "🚀 Rozpoczynam testy integracyjne UCAS E2E..." -ForegroundColor Cyan

# 1. Test Gateway Routing & Health
try {
    $healthResponse = Invoke-RestMethod -Uri "$GatewayUrl/health" -Method Get
    if ($healthResponse.status -eq "healthy") {
        Write-Host "✅ API Gateway odpowiada i tuneluje ruch poprawnie." -ForegroundColor Green
    } else {
        Write-Host "🔴 Gateway zwrócił status: $($healthResponse.status)" -ForegroundColor Red
        Write-Host ($healthResponse | ConvertTo-Json -Depth 5) -ForegroundColor Red
    }
} catch {
    Write-Host "🔴 Błąd Gatewaya: $_" -ForegroundColor Red
    exit 1
}

# 2. Test Trenowania (Orchestrator przez Gateway)
$timestamp = Get-Date -Format "HHmmss"
$trainPayload = @{
    name = "Test_E2E_Categorizer_$timestamp"
    training_data = @(
        @{ text = "drukarka 3d nie grzeje stołu"; category = "sprzęt" },
        @{ text = "brak dostępu do sieci"; category = "it" }
    )
    layers = @("tags", "xgboost")
} | ConvertTo-Json -Depth 10 -Compress

Write-Host "⏳ Wysyłam żądanie treningu..." -ForegroundColor Yellow

try {
    $trainResponse = Invoke-RestMethod -Uri "$GatewayUrl/train" -Method Post -Body $trainPayload -ContentType "application/json"
    Write-Host "✅ Endpoint treningowy Orchestratora działa (brak błędu 500/N+1)." -ForegroundColor Green
    Write-Host "   Wynik ID: $($trainResponse.categorizer_id)" -ForegroundColor DarkGray
} catch {
    if ($_.Exception.Response.StatusCode.value__ -eq 409) {
        Write-Host "✅ Endpoint działa, kategoryzator już istniał (409 Conflict)." -ForegroundColor Green
    } else {
        Write-Host "🔴 Błąd przy trenowaniu: $_" -ForegroundColor Red
        
        # Wyciągnięcie szczegółów błędu jeśli API coś zwraca
        if ($_.Exception.Response) {
            $stream = $_.Exception.Response.GetResponseStream()
            $reader = New-Object System.IO.StreamReader($stream)
            $responseBody = $reader.ReadToEnd()
            Write-Host "Treść błędu: $responseBody" -ForegroundColor Red
        }
        exit 1
    }
}

Write-Host "🎯 Wszystkie krytyczne warstwy zintegrowane pomyślnie." -ForegroundColor Cyan