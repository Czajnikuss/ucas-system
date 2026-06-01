# Embeddings Service

Generuje wektory (embeddingi) tekstu używane do wyszukiwania semantycznego (RAG) oraz
oceny jakości próbek (Evaluator). Model wielojęzyczny, więc dobrze radzi sobie z językiem
polskim.

## Port
- **8050** (host i kontener).

## Model
- `paraphrase-multilingual-MiniLM-L12-v2` (sentence-transformers)
- Wymiar wektora: **384** (zgodny z `training_samples.embedding VECTOR(384)` w bazie)

## Endpointy
| Metoda | Ścieżka | Opis |
|---|---|---|
| GET | `/` | Info o serwisie i modelu |
| GET | `/health` | Status + nazwa/wymiar modelu |
| POST | `/embed` | `{texts:[str], normalize:bool}` → `{embeddings:[[float]], model, dimensions}` |
| POST | `/similarity` | Podobieństwo kosinusowe między tekstami |
| GET | `/model/info` | Szczegóły modelu |

## Zmienne środowiskowe
Brak wymaganych (model pobierany przy starcie; cache w obrazie/wolumenie).

## Zależności
Brak (samodzielny). Wołany przez: **orchestrator** (trening – generacja embeddingów),
**rag-service** (`/search`), **evaluator** (ocena jakości).

## Uruchomienie i test (Podman)
```powershell
podman compose up -d embeddings-service
curl http://localhost:8050/health
$b = @{ texts = @("nie moge sie zalogowac"); normalize = $true } | ConvertTo-Json
Invoke-RestMethod -Uri http://localhost:8050/embed -Method Post -Body $b -ContentType application/json
```
