# RAG Service

Dedykowana warstwa RAG (Retrieval-Augmented Generation). Dla zadanego tekstu zwraca
najbardziej podobne **aktywne** próbki treningowe kategoryzatora (wyszukiwanie wektorowe
pgvector). Wynik jest wstrzykiwany jako kontekst few-shot do promptu warstwy LLM.

## Port
- **8070** (host i kontener). Swagger: http://localhost:8070/swagger

## Endpointy
| Metoda | Ścieżka | Opis |
|---|---|---|
| GET | `/health` | Status serwisu |
| POST | `/search` | `{categorizer_id, query_text, top_k}` → `{categorizer_id, query_text, samples:[{text,category,similarity}], count}` |
| POST | `/inject` | Wstawia próbkę z gotowym wektorem: `{categorizer_id, text, category, embedding:[float]}` → `{status, inserted_id}` |

`/search` sam liczy embedding zapytania (woła `embeddings-service`), więc klient nie dostarcza wektora.
`categorizer_id` może być slugiem **lub** nazwą kategoryzatora (mapowane na UUID z tabeli `categorizers`).

## Zmienne środowiskowe
| Zmienna | Domyślnie | Opis |
|---|---|---|
| `DATABASE_URL` | `postgresql://ucas_user:...@postgres:5432/ucas_db` | Połączenie z Postgres (pgvector) |
| `EMBEDDINGS_SERVICE_URL` | `http://embeddings-service:8050` | Adres serwisu embeddingów |

## Zależności
- **postgres** (pgvector, tabele `categorizers`, `training_samples.embedding VECTOR(384)`)
- **embeddings-service** (`/embed`)

Wołany przez: **llm-layer** (`POST /search`) podczas klasyfikacji kaskadowej.

## Uruchomienie i test (Podman)
```powershell
podman compose up -d rag-service
curl http://localhost:8070/health
```
Test wyszukiwania (po wytrenowaniu kategoryzatora z embeddingami):
```powershell
$b = @{ categorizer_id = "demo-helpdesk-routing"; query_text = "nie moge sie zalogowac"; top_k = 3 } | ConvertTo-Json
Invoke-RestMethod -Uri http://localhost:8070/search -Method Post -Body $b -ContentType application/json
```
