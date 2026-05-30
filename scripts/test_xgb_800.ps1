$ErrorActionPreference = "Stop"
$GatewayUrl = "http://localhost:8000"
$CategorizerName = "E2E-Master-All-Layers"

Write-Host "START: Test E2E UCAS (Kaskada + Fallback)" -ForegroundColor Cyan

if (-not (Test-Path "train_data.json")) {
    Write-Host "ERROR: Brak pliku train_data.json." -ForegroundColor Red
    exit 1
}

$JsonContent = Get-Content -Path "train_data.json" -Raw -Encoding UTF8
$Payload = $JsonContent | ConvertFrom-Json

# Bierzemy resztę z pliku JSON bez nadpisywania
$Payload.name = $CategorizerName

$BodyString = $Payload | ConvertTo-Json -Depth 10 -Compress
$BodyBytes = [System.Text.Encoding]::UTF8.GetBytes($BodyString)

Write-Host "WAIT: Inicjalizacja kategoryzatora (trening/odczyt)..." -ForegroundColor Yellow

$CategorizerId = $null

try {
    $response = Invoke-RestMethod -Uri "$GatewayUrl/train" -Method Post -Body $BodyBytes -ContentType "application/json; charset=utf-8"
    $CategorizerId = $response.categorizer_id
    Write-Host "OK: Wytrenowano nowy kategoryzator: $CategorizerId" -ForegroundColor Green
} catch {
    if ($_.Exception.Response.StatusCode.value__ -eq 409) {
        $stream = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        $rawErr = $reader.ReadToEnd()
        
        $errBody = $rawErr | ConvertFrom-Json
        
        if ($errBody.detail.existing_categorizer.categorizer_id) {
            $CategorizerId = $errBody.detail.existing_categorizer.categorizer_id
        } else {
            # 🎯 FIX: Wymuszenie formatu slug jak w Orchestratorze
            $CategorizerId = $CategorizerName.ToLower().Replace(" ", "-")
        }
        Write-Host "✅ Kategoryzator juz istnieje. Przechwycono ID: $CategorizerId" -ForegroundColor Green
    } else {
        Write-Host "ERROR: Krytyczny blad przy trenowaniu: $_" -ForegroundColor Red
        if ($_.Exception.Response) {
            $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
            Write-Host $reader.ReadToEnd() -ForegroundColor Red
        }
        exit 1
    }
}

$TestText = "Aplikacja zawiesza sie przy generowaniu raportu i zjada caly RAM."

# ==========================================
# TEST 1: KASKADA
# ==========================================
Write-Host "`nWAIT: Test 1 -> Strategia 'cascade'..." -ForegroundColor Yellow

$CascadePayload = @{
    categorizer_id = $CategorizerId
    text = $TestText
    strategy = "cascade"
    return_prompt = $true
} | ConvertTo-Json -Compress

$CascadeBytes = [System.Text.Encoding]::UTF8.GetBytes($CascadePayload)

try {
    $classResult = Invoke-RestMethod -Uri "$GatewayUrl/classify" -Method Post -Body $CascadeBytes -ContentType "application/json; charset=utf-8"
    Write-Host "OK: Wynik Kaskady:" -ForegroundColor Green
    Write-Host "   Kategoria: $($classResult.category) | Pewnosc: $($classResult.confidence)" -ForegroundColor Cyan
    Write-Host "   Zrodlo (method): $($classResult.method)" -ForegroundColor Magenta
    
    Write-Host "   --- HISTORIA PRZEBIEGU KASKADY ---" -ForegroundColor Yellow
    Write-Host ($classResult.layer_results | ConvertTo-Json -Depth 5 -Compress) -ForegroundColor DarkGray
} catch {
    Write-Host "ERROR: Blad przy kaskadzie: $_" -ForegroundColor Red
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        Write-Host $reader.ReadToEnd() -ForegroundColor Red
    }
}

# ==========================================
# TEST 2: XGBOOST
# ==========================================
Write-Host "`nWAIT: Test 2 -> Izolacja 'xgboost'..." -ForegroundColor Yellow

$XgbPayload = @{
    categorizer_id = $CategorizerId
    text = $TestText
    strategy = "xgboost"
} | ConvertTo-Json -Compress

$XgbBytes = [System.Text.Encoding]::UTF8.GetBytes($XgbPayload)

try {
    $xgbResult = Invoke-RestMethod -Uri "$GatewayUrl/classify" -Method Post -Body $XgbBytes -ContentType "application/json; charset=utf-8"
    Write-Host "OK: Surowy wynik XGBoost:" -ForegroundColor Green
    Write-Host "   Kategoria: $($xgbResult.category) | Pewnosc: $($xgbResult.confidence)" -ForegroundColor Cyan
} catch {
    Write-Host "ERROR: Blad przy bezposrednim strzale do XGBoost: $_" -ForegroundColor Red
}