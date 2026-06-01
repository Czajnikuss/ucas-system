# Postgres (pgvector)

Baza danych UCAS oparta na obrazie `pgvector/pgvector:pg16`. Przechowuje kategoryzatory,
próbki treningowe (z wektorami `VECTOR(384)`), historię klasyfikacji, recenzje HIL,
webhooki i przebiegi kuracji.

## Port
- **5432** (host i kontener). DB: `ucas_db`, user: `ucas_user`.

## Źródło prawdy o schemacie
`init.sql` jest **jedynym źródłem prawdy** dla schematu. Uruchamiany jednorazowo przy
pierwszej inicjalizacji wolumenu (`/docker-entrypoint-initdb.d/`). Modele ORM w serwisach
(`orchestrator/models/database.py`, inline w `hil-layer`/`evaluator`) **muszą być z nim
zgodne** — `Base.metadata.create_all` nie modyfikuje istniejących tabel (nie dodaje kolumn).

> Po zmianie `init.sql` na istniejącym wolumenie zmiany **nie** zastosują się automatycznie.
> Trzeba albo zresetować wolumen (`podman volume rm`), albo wykonać ręczną migrację `ALTER TABLE`.

## Kluczowe tabele
| Tabela | Rola |
|---|---|
| `categorizers` | Definicje kategoryzatorów (slug, kategorie, warstwy, config) |
| `training_samples` | Próbki treningowe + `embedding VECTOR(384)`, `is_active`, `quality_score` |
| `classifications` | Historia klasyfikacji (w tym `llm_prompt`) |
| `hil_reviews` | Kolejka i decyzje Human-in-the-Loop |
| `curation_runs` | Historia kuracji danych |
| `webhooks`, `webhook_deliveries` | Rejestr webhooków i dostarczeń |

## Funkcje pomocnicze (pgvector)
- `search_similar_samples(query_embedding, categorizer_uuid, threshold, limit)` — wyszukiwanie podobnych aktywnych próbek.
- `count_unscored_samples(cat_id)`, `get_curation_iteration(cat_id)`, `needs_reevaluation(cat_id)`.

## Reset i podgląd (Podman)
```powershell
podman compose up -d postgres
podman exec ucas-postgres psql -U ucas_user -d ucas_db -c "\dt"
# Pełny reset bazy (UWAGA: kasuje dane):
# podman compose down; podman volume rm ucas-system_postgres
```
