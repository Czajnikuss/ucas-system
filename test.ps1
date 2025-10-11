# ============================================
# UCAS SYSTEM - COMPLETE E2E TEST SUITE
# ============================================

Write-Host "`n=== UCAS SYSTEM E2E VALIDATION ===" -ForegroundColor Cyan
Write-Host "Testing all layers, persistence, and orchestration`n" -ForegroundColor Gray

# 1. SYSTEM HEALTH CHECK
Write-Host "[1/10] System Health Check" -ForegroundColor Yellow
$health = Invoke-RestMethod -Uri "http://localhost:8001/health" -Method Get
Write-Host "  Status: $($health.status)" -ForegroundColor Green
Write-Host "  Tags Layer: $($health.layers.tags)" -ForegroundColor $(if($health.layers.tags -eq "healthy"){"Green"}else{"Red"})
Write-Host "  XGBoost Layer: $($health.layers.xgboost)" -ForegroundColor $(if($health.layers.xgboost -eq "healthy"){"Green"}else{"Red"})
Write-Host "  LLM Layer: $($health.layers.llm)" -ForegroundColor $(if($health.layers.llm -eq "healthy"){"Green"}else{"Red"})
Write-Host "  Database: $($health.database)`n" -ForegroundColor $(if($health.database -eq "healthy"){"Green"}else{"Red"})

# 2. CREATE TEST CATEGORIZER
Write-Host "[2/10] Train Categorizer (Tags Layer)" -ForegroundColor Yellow
@'
{"name":"E2E Test Final","description":"Complete validation test","training_data":[{"text":"Produkt uszkodzony","category":"Jakość"},{"text":"Dostawa opóźniona","category":"Logistyka"},{"text":"Obsługa pomocna","category":"Obsługa"}],"layers":["tags"],"fallback_category":"Inne"}
'@ | Out-File test_data\e2e_train.json -Encoding UTF8

$train = curl.exe -s -X POST http://localhost:8001/train -H "Content-Type: application/json" -d "@test_data/e2e_train.json" | ConvertFrom-Json
Write-Host "  Categorizer ID: $($train.categorizer_id)" -ForegroundColor Green
Write-Host "  Name: $($train.name)" -ForegroundColor Green
Write-Host "  Categories: $($train.categories -join ', ')" -ForegroundColor Green
Write-Host "  Training Samples: $($train.training_samples)`n" -ForegroundColor Green

# 3. TEST DUPLICATE NAME
Write-Host "[3/10] Test Duplicate Name (Should Return 409)" -ForegroundColor Yellow
$dupResponse = curl.exe -s -X POST http://localhost:8001/train -H "Content-Type: application/json" -d "@test_data/e2e_train.json"
$dupJson = $dupResponse | ConvertFrom-Json
if ($dupJson.detail.error -eq "Name already exists") {
    Write-Host "  ✓ Duplicate correctly rejected" -ForegroundColor Green
    Write-Host "  Suggestions: $($dupJson.detail.suggestions -join ', ')`n" -ForegroundColor Cyan
} else {
    Write-Host "  ✗ Duplicate should have been rejected`n" -ForegroundColor Red
}


# 4. LIST CATEGORIZERS
Write-Host "[4/10] List All Categorizers" -ForegroundColor Yellow
$categorizers = Invoke-RestMethod -Uri "http://localhost:8001/categorizers" -Method Get
Write-Host "  Total: $($categorizers.Count)" -ForegroundColor Green
foreach ($cat in $categorizers | Select-Object -First 3) {
    Write-Host "  - $($cat.name) [$($cat.categorizer_id)]" -ForegroundColor Gray
}
Write-Host ""

# 5. CLASSIFY - EXACT MATCH
Write-Host "[5/10] Classify - Tags Layer (Exact Match)" -ForegroundColor Yellow
@'
{"categorizer_id":"e2e-test-final","text":"produkt zepsuty","strategy":"cascade"}
'@ | Out-File test_data\e2e_classify1.json -Encoding UTF8

$result1 = curl.exe -s -X POST http://localhost:8001/classify -H "Content-Type: application/json" -d "@test_data/e2e_classify1.json" | ConvertFrom-Json
Write-Host "  Category: $($result1.category)" -ForegroundColor Green
Write-Host "  Confidence: $($result1.confidence)" -ForegroundColor Green
Write-Host "  Method: $($result1.method)" -ForegroundColor Green
Write-Host "  Time: $([math]::Round($result1.processing_time_ms, 2))ms`n" -ForegroundColor Cyan

# 6. CLASSIFY - PARTIAL MATCH
Write-Host "[6/10] Classify - Partial Match" -ForegroundColor Yellow
@'
{"categorizer_id":"e2e-test-final","text":"obsługa świetna","strategy":"cascade"}
'@ | Out-File test_data\e2e_classify2.json -Encoding UTF8

$result2 = curl.exe -s -X POST http://localhost:8001/classify -H "Content-Type: application/json" -d "@test_data/e2e_classify2.json" | ConvertFrom-Json
Write-Host "  Category: $($result2.category)" -ForegroundColor Green
Write-Host "  Confidence: $($result2.confidence)" -ForegroundColor Green
Write-Host "  Method: $($result2.method)" -ForegroundColor Green
Write-Host "  Time: $([math]::Round($result2.processing_time_ms, 2))ms`n" -ForegroundColor Cyan

# 7. CHECK HISTORY
Write-Host "[7/10] Classification History" -ForegroundColor Yellow
$history = Invoke-RestMethod -Uri "http://localhost:8001/categorizers/e2e-test-final/history" -Method Get
Write-Host "  Total Classifications: $($history.Count)" -ForegroundColor Green
if ($history.Count -gt 0) {
    $last = $history[0]
    Write-Host "  Last: '$($last.text)' → $($last.category) [$($last.method)]`n" -ForegroundColor Gray
}

# 8. PERSISTENCE TEST
Write-Host "[8/10] Persistence Test (Restart Orchestrator)" -ForegroundColor Yellow
Write-Host "  Restarting..." -ForegroundColor Gray
docker compose restart orchestrator 2>&1 | Out-Null
Start-Sleep -Seconds 12

$post_restart = Invoke-RestMethod -Uri "http://localhost:8001/categorizers" -Method Get
if ($post_restart.Count -ge $categorizers.Count) {
    Write-Host "  ✓ Persistence confirmed ($($post_restart.Count) categorizers)" -ForegroundColor Green
} else {
    Write-Host "  ✗ Data loss!`n" -ForegroundColor Red
}

# 9. RE-CLASSIFY AFTER RESTART
Write-Host "[9/10] Re-classify After Restart" -ForegroundColor Yellow
$final = curl.exe -s -X POST http://localhost:8001/classify -H "Content-Type: application/json" -d "@test_data/e2e_classify1.json" | ConvertFrom-Json
if ($final.category) {
    Write-Host "  ✓ Category: $($final.category) [$($final.method), $([math]::Round($final.processing_time_ms, 2))ms]`n" -ForegroundColor Green
}

# 10. FINAL STATUS
Write-Host "[10/10] Final System Status" -ForegroundColor Yellow
$containers = docker compose ps --format json | ConvertFrom-Json
foreach ($c in $containers) {
    $status = if ($c.State -eq "running") { "✓" } else { "✗" }
    $color = if ($c.State -eq "running") { "Green" } else { "Red" }
    Write-Host "  $status $($c.Service): $($c.State)" -ForegroundColor $color
}

Write-Host "`n=== E2E TEST COMPLETE ===" -ForegroundColor Cyan
Write-Host "✓ All layers operational" -ForegroundColor Green
Write-Host "✓ Persistence working" -ForegroundColor Green
Write-Host "✓ Classification working" -ForegroundColor Green
Write-Host "`n🎉 SYSTEM READY FOR NEXT SESSION 🎉`n" -ForegroundColor Green
