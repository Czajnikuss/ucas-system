# Dashboard Admin (Streamlit)

Panel zarządzania UCAS w Streamlit. Główny interfejs operatora: przegląd kategoryzatorów,
edycja danych treningowych, interaktywne testy klasyfikacji i statystyki kaskady.

## Port
- **8080** (host i kontener): http://localhost:8080

## Zakładki
- **🗄️ Modele** — lista kategoryzatorów, usuwanie.
- **🗂️ Dane Treningowe** — edycja danych, import CSV (Overwrite/Append), podzakładka **Ocena Jakości (Evaluator)**.
- **🧪 Test API** — dowolny tekst + wybór strategii (`cascade`/`llm`/`xgboost`/`tags`); podgląd pełnego JSON i **promptu LLM z wstrzykniętym kontekstem RAG**.
- **📊 Statystyki & Historia** — dystrybucja warstw, czasy, ostatnie 50 klasyfikacji.

## Uruchomienie
Kontener startuje przez `streamlit run app.py` (definicja `command` w docker-compose.yml).
Plik `main.py`/`templates` (stary wariant FastAPI) został usunięty — **żywy jest tylko `app.py`**.

## Zmienne środowiskowe
| Zmienna | Domyślnie | Opis |
|---|---|---|
| `ORCHESTRATOR_URL` | `http://orchestrator:8001` | API orchestratora (przez nie idą wywołania) |
| `EVALUATOR_URL` | `http://evaluator:8060` | Ocena jakości próbek |

## Zależności
- **orchestrator** (8001) — kategoryzatory, trening, klasyfikacja, statystyki
- **evaluator** (8060) — scoring jakości

## Uruchomienie i test (Podman)
```powershell
podman compose up -d dashboard-admin
# Otwórz w przeglądarce:
start http://localhost:8080
```
