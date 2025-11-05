# ============================================
# HIL WEBHOOK TEST SCRIPT
# ============================================

Write-Host "`n=== HIL WEBHOOK TEST ===" -ForegroundColor Cyan

# 1. Register webhook
Write-Host "`n[1] Registering webhook..." -ForegroundColor Yellow

$webhookData = @{
    name = "Test System"
    url = "http://webhook.site/your-unique-id"
    description = "Integration test webhook"
} | ConvertTo-Json

try {
    $reg = Invoke-RestMethod "http://localhost:8040/webhooks/register" `
        -Method POST `
        -Body $webhookData `
        -ContentType "application/json"
    
    Write-Host "  ✓ Registered: $($reg.url)" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# 2. List webhooks
Write-Host "`n[2] Listing webhooks..." -ForegroundColor Yellow

try {
    $list = Invoke-RestMethod "http://localhost:8040/webhooks"
    Write-Host "  ✓ Total: $($list.count)" -ForegroundColor Green
    
    foreach ($wh in $list.webhooks) {
        Write-Host "    - $($wh.name)" -ForegroundColor Gray
    }
} catch {
    Write-Host "  ✗ Failed" -ForegroundColor Red
}

# 3. Test webhook
Write-Host "`n[3] Sending test payload..." -ForegroundColor Yellow

try {
    $webhookId = $list.webhooks[0].webhook_id
    $test = Invoke-RestMethod "http://localhost:8040/webhooks/$webhookId/test" -Method POST
    
    Write-Host "  ✓ Status: $($test.status)" -ForegroundColor Green
    Write-Host "    Response: $($test.response_code)" -ForegroundColor Gray
} catch {
    Write-Host "  ✗ Failed" -ForegroundColor Red
}

Write-Host "`n=== TEST COMPLETE ===" -ForegroundColor Green
