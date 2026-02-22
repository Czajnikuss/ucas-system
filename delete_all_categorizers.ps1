$ErrorActionPreference = "Stop"
$GatewayUrl = "http://localhost:8000"

Write-Host "WAIT: Pobieranie listy kategoryzatorow z bazy..." -ForegroundColor Yellow

try {
    # Uderzamy w endpoint zdefiniowany w management.py
    $categorizers = Invoke-RestMethod -Uri "$GatewayUrl/categorizers" -Method Get
    
    if (-not $categorizers -or $categorizers.count -eq 0) {
        Write-Host "OK: Brak kategoryzatorow w bazie. Czysto." -ForegroundColor Green
        exit 0
    }
    
    Write-Host "Znaleziono kategoryzatory:" -ForegroundColor Cyan
    $categorizers | Format-Table -Property categorizer_id, name, created_at

    Write-Host "`nWAIT: Rozpoczynam czyszczenie..." -ForegroundColor Yellow

    foreach ($cat in $categorizers) {
        $catId = $cat.categorizer_id
        Write-Host "   -> Usuwam: $catId" -ForegroundColor DarkGray
        try {
            Invoke-RestMethod -Uri "$GatewayUrl/categorizers/$catId" -Method Delete | Out-Null
            Write-Host "   ✅ Usunieto: $catId" -ForegroundColor Green
        } catch {
            Write-Host "   🔴 Blad przy usuwaniu $catId : $_" -ForegroundColor Red
        }
    }
    
    Write-Host "`nOK: Czyszczenie zakonczone. Srodowisko gotowe na nowy trening." -ForegroundColor Green

} catch {
    Write-Host "🔴 Blad krytyczny API (czy endpoint /categorizers istnieje w API Gateway?): $_" -ForegroundColor Red
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        Write-Host $reader.ReadToEnd() -ForegroundColor Red
    }
}