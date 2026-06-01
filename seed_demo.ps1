# seed_demo.ps1 — Uruchamia gotowe demo "pod klucz" dla partnera.
# Trenuje kategoryzator routingu zgłoszeń helpdesk i pokazuje działanie kaskady.
# Wymaga uruchomionego stacka: docker compose up -d

$ErrorActionPreference = "Stop"
$GatewayUrl = "http://localhost:8000"
$DataFile   = "demo/helpdesk_demo.json"

Write-Host "=== UCAS DEMO: Routing zgłoszeń Helpdesk ===" -ForegroundColor Cyan

if (-not (Test-Path $DataFile)) {
    Write-Host "ERROR: Brak pliku $DataFile" -ForegroundColor Red
    exit 1
}

# --- 1. Trening kategoryzatora ---
$Payload    = Get-Content -Path $DataFile -Raw -Encoding UTF8 | ConvertFrom-Json
$BodyString = $Payload | ConvertTo-Json -Depth 10 -Compress
$BodyBytes  = [System.Text.Encoding]::UTF8.GetBytes($BodyString)

Write-Host "`n[1/2] Trenuję kategoryzator '$($Payload.name)'..." -ForegroundColor Yellow

$CategorizerId = $null
try {
    $resp = Invoke-RestMethod -Uri "$GatewayUrl/train" -Method Post -Body $BodyBytes -ContentType "application/json; charset=utf-8"
    $CategorizerId = $resp.categorizer_id
    Write-Host "OK: Wytrenowano nowy kategoryzator: $CategorizerId" -ForegroundColor Green
} catch {
    if ($_.Exception.Response.StatusCode.value__ -eq 409) {
        # Body bledu: najpierw ErrorDetails.Message (dziala w PS 5.1 i 7+),
        # potem strumien odpowiedzi, na koncu fallback na nazwe (classify akceptuje nazwe LUB slug).
        $raw = $_.ErrorDetails.Message
        if (-not $raw) {
            try { $raw = (New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())).ReadToEnd() } catch {}
        }
        if ($raw) {
            try { $CategorizerId = ($raw | ConvertFrom-Json).detail.existing_categorizer.categorizer_id } catch {}
        }
        if (-not $CategorizerId) { $CategorizerId = $Payload.name }
        Write-Host "OK: Kategoryzator już istnieje. ID: $CategorizerId" -ForegroundColor Green
    } else {
        Write-Host "ERROR: Trening nie powiódł się: $_" -ForegroundColor Red
        exit 1
    }
}

# --- 2. Klasyfikacja przykładowych zgłoszeń (strategia cascade) ---
$Samples = @(
    "Zapomniałem hasła i nie mogę wejść do systemu.",
    "Proszę o korektę faktury, kwota jest zawyżona.",
    "Aplikacja crashuje przy zapisie zamówienia.",
    "Mój laptop się nie uruchamia od rana.",
    "Czy aplikacja działa na iPhonie?"
)

Write-Host "`n[2/2] Klasyfikuję przykładowe zgłoszenia:" -ForegroundColor Yellow

foreach ($text in $Samples) {
    $cp = @{ categorizer_id = $CategorizerId; text = $text; strategy = "cascade" } | ConvertTo-Json -Compress
    $cb = [System.Text.Encoding]::UTF8.GetBytes($cp)
    try {
        $r = Invoke-RestMethod -Uri "$GatewayUrl/classify" -Method Post -Body $cb -ContentType "application/json; charset=utf-8"
        $conf = [math]::Round([double]$r.confidence, 2)
        Write-Host ("  • [{0,-16}] conf={1,-4} via {2,-8} :: {3}" -f $r.category, $conf, $r.method, $text) -ForegroundColor Cyan
    } catch {
        Write-Host "  • ERROR dla '$text': $_" -ForegroundColor Red
    }
}

Write-Host "`nGotowe. Panel zarządzania: http://localhost:8080" -ForegroundColor Green
Write-Host "Swagger API: http://localhost:8000/swagger" -ForegroundColor Green
