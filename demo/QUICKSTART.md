# UCAS — Demo w 10 minut (dla partnera)

Cel: w ciągu 10 minut pokazać działającą kaskadę klasyfikacji na realistycznym
przykładzie (routing zgłoszeń helpdesk), w pełni lokalnie.

## Wymagania
- Docker & Docker Compose (V2), min. 8 GB RAM (16 GB zalecane dla LLM)
- PowerShell (Windows) lub dowolny klient REST

## Krok 1 — uruchom stack (~3–5 min, pierwszy raz dłużej: pobranie obrazów + modelu)
```powershell
docker compose up -d
```
Poczekaj aż usługi wstaną. Sprawdź zdrowie systemu:
```powershell
curl http://localhost:8000/health
```

## Krok 2 — załaduj demo i zobacz kaskadę (~2 min)
```powershell
.\seed_demo.ps1
```
Skrypt wytrenuje kategoryzator `Demo-Helpdesk-Routing` (8 kategorii: Dostęp i Konto,
Płatności i Faktury, Błąd Aplikacji, Sprzęt, Sieć i Łączność, Email i Komunikacja,
Instalacja i Konfiguracja, Zapytanie Ogólne; ~680 próbek) i sklasyfikuje kilka
przykładowych zgłoszeń. Zobaczysz, którą **warstwą** (`tags` / `xgboost` / `llm`)
system rozwiązał każde zgłoszenie i z jaką pewnością.

## Krok 3 — panel zarządzania (~3 min)
Otwórz **http://localhost:8080** (Streamlit). Zakładki:
- **Modele** — lista kategoryzatorów, usuwanie.
- **Dane Treningowe** — edycja, import CSV (Overwrite/Append), przeliczenie kaskady.
- **Test API** — wpisz dowolne zgłoszenie, wybierz strategię (`cascade` / `llm` / `xgboost` / `tags`),
  podejrzyj wygenerowany prompt LLM z wstrzykniętym kontekstem RAG.
- **Statystyki & Historia** — czas procesowania, dystrybucja warstw, ostatnie zapytania.

## Krok 4 — własny przykład przez API
```powershell
$body = @{ categorizer_id = "demo-helpdesk-routing"; text = "Drukarka nie drukuje, miga dioda"; strategy = "cascade" } | ConvertTo-Json -Compress
$bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
Invoke-RestMethod -Uri "http://localhost:8000/classify" -Method Post -Body $bytes -ContentType "application/json; charset=utf-8"
```

## Co podkreślić na demo
1. **Koszt** — większość zgłoszeń łapią `tags`/`xgboost` (milisekundy, zero kosztu LLM).
2. **Prywatność** — wszystko działa lokalnie, żadne dane nie wychodzą na zewnątrz.
3. **Human-in-the-Loop** — niepewne przypadki da się eskalować do człowieka (webhooki).
4. **Samodoskonalenie** — poprawione przez człowieka próbki wracają do treningu.
