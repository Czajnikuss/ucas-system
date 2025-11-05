# UCAS System — Programming References (inwentaryzacja)

Ten plik zawiera szczegółową inwentaryzację serwisów, plików konfiguracyjnych i punktów wejścia do edycji. Przydatne, gdy chcesz szybko zrozumieć co gdzie zmienić.

> Uwaga: dokumentacja opiera się na aktualnych plikach w repo (gł. `services/*/main.py`, `docker-compose.yml`, `config/config.yaml`). W repo stwierdziłem kilka niespójności (np. mapowanie portów) — poniżej są oznaczone jako "UWAGA: mismatch" wraz z lokalizacją, gdzie port jest ustawiony.

---

## Główne pliki konfiguracyjne

- `docker-compose.yml` (root) — orkiestracja kontenerów, mapowanie portów, zależności między usługami, wolumeny.
- `config/config.yaml` — centralna konfiguracja Orchestratora i parametrów systemowych (cascade thresholds, URLs warstw, curation/quality settings, dashboady).
- `config/secrets.yaml` — (lokalny) przykładowy plik z hasłami (postgre, redis) — nie commituj prawdziwych sekretów.

Gdy chcesz szybko znaleźć ustawienia systemowe (np. URL do warstwy LLM), sprawdź `config/config.yaml` (sekcja `orchestrator.layers`). Orchestrator korzysta z tego pliku (przez `config_loader.py`).

---

## Lista serwisów (skrót)

Dla każdego serwisu: lokalizacja, cel, kluczowe endpointy, zmienne środowiskowe i pliki do edycji.

### 1) API Gateway
- Ścieżka: `services/api-gateway/main.py`
- Cel: prosty proxy / jednolity punkt wejścia. Przekazuje żądania do Orchestratora.
- Key endpoints:
  - `GET /` — status
  - `GET /health` — health check (sprawdza Redis i Orchestrator)
  - `POST /api/v1/categorizers/initialize` — forward do Orchestratora
  - `GET /api/v1/categorizers` — forward
- Env vars:
  - `REDIS_HOST` (default: `redis`)
  - `REDIS_PASSWORD` (default: `ucas_redis_pass`)
  - `ORCHESTRATOR_URL` (domyślnie `http://orchestrator:8001`)
- Port uruchomieniowy (uvicorn): 8000 (w `if __name__ == "__main__"`)
- Docker mapping (`docker-compose.yml`): `8000:8000` (zgodne)
- Gdzie edytować: `services/api-gateway/main.py` i ewentualnie `Dockerfile`.

### 2) Orchestrator
- Ścieżka: `services/orchestrator/main.py` (+ `services/orchestrator/config_loader.py`, `services/orchestrator/README.md`)
- Cel: centralny koordynator cascade, triggery persistence, REST API agregujące funkcje zarządzania i klasyfikacji.
- Key endpoints:
  - `GET /` — info
  - `GET /health` — sprawdza warstwy określone w config
  - routery z `api/` folderu: training, management, classification, analytics, rag
- Gdzie jest konfiguracja: `config/config.yaml` (sekcja `orchestrator`), a `config_loader.py` ładuje ustawienia
- Port: konfigurowalny — `orchestrator.service.port` w `config/config.yaml` (domyślnie 8001). `docker-compose.yml` mapuje `8001:8001`.
- Notatki: w `startup` Orchestratora znajduje się logika przywracania stanu z dysku (persistence) — sprawdź `persistence.py`.

### 3) Tags Layer
- Ścieżka: `services/tags-layer/main.py`
- Cel: prosty, szybki ekstraktor słów-kluczy / dopasowań (Polish-optimized)
- Key endpoints:
  - `GET /` — info
  - `GET /health` — health
  - `POST /train` — trenowanie słowników słów-kluczy (zwraca `keywords`)
  - `POST /classify` — klasyfikacja przez dopasowanie słów
  - `GET /categorizers/{id}/keywords` — pobiera słowa dla danego categorizer
- Port (uvicorn): domyślnie 8010 — `docker-compose.yml` mapuje `8010:8010` (zgodne)
- Gdzie edytować: `services/tags-layer/main.py`

### 4) XGBoost Layer
- Ścieżka: `services/xgboost-layer/main.py`
- Cel: klasyfikator ML z Word2Vec + XGBoost, potrafi trenować i klasyfikować batchy
- Key endpoints:
  - `GET /` — info
  - `GET /health`
  - `POST /train` — trenowanie modelu (wymaga >= 2 próbek)
  - `POST /classify` — klasyfikacja tekstu
  - `GET /categorizers/{id}/info` — info o modelu
- Port (uvicorn): w kodzie `uvicorn.run(..., port=8020)`
- Docker mapping: `docker-compose.yml` ma `8020:8003` — UWAGA: mismatch (internal port w docker-compose jest 8003, ale w `main.py` uruchamiany jest 8020). Należy ujednolicić przed wdrożeniem.
- Gdzie edytować: `services/xgboost-layer/main.py`, modele zapisują się w `/data/models` wewnątrz kontenera.

### 5) LLM Layer
- Ścieżka: `services/llm-layer/main.py`
- Cel: klasyfikacja oparta na LLM (Ollama), z obsługą fallback_category i prostą konfiguracją GPU
- Key endpoints:
  - `GET /` — info
  - `GET /health` — sprawdza połączenie z Ollama
  - `POST /train` — zapisuje przykłady i konfigurację (few-shot)
  - `POST /classify` — klasyfikacja z opcjonalnym RAG (wywołuje `rag-service`)
  - `GET /categorizers/{id}/info`
- Port (uvicorn): w kodzie `uvicorn.run(..., port=8030)`
- Docker mapping: `docker-compose.yml` ma `8030:8004` — UWAGA: mismatch (internal vs kod)
- Env vars / zależności: `OLLAMA_URL` (domyślnie `http://ollama:11434`)
- Gdzie edytować: `services/llm-layer/main.py`

### 6) HIL Layer
- Ścieżka: `services/hil-layer/main.py`, dodatkowo `services/hil-layer/webhooks.py`, `services/hil-layer/models/` (DB models dla HIL)
- Cel: obsługa eskalacji do człowieka, CRUD recenzji, rejestracja i wywoływanie webhooków
- Key endpoints:
  - `GET /` — info
  - `GET /health`
  - `POST /escalate` — eskalacja (dodaje wpis do DB i wywołuje webhooki)
  - `GET /pending` — lista pending reviews
  - `POST /review/{review_id}` — submit review, dodaje próbkę do treningu
  - Webhooks: `POST /webhooks/register`, `GET /webhooks`, `DELETE /webhooks/{id}`, `POST /webhooks/{id}/test`
- Port (uvicorn): 8040 — `docker-compose.yml` mapuje `8040:8040` (zgodne)
- Gdzie edytować: `services/hil-layer/main.py`, `services/hil-layer/webhooks.py` (logika dostawców webhooków i retry)

### 7) Embeddings Service
- Ścieżka: `services/embeddings-service/main.py`
- Cel: generowanie embeddingów (SentenceTransformers) oraz endpoint `/embed` i `/similarity`
- Key endpoints:
  - `GET /` — info
  - `GET /health` — sprawdza czy model załadowany
  - `POST /embed` — generuje embeddingi dla listy tekstów
  - `POST /similarity` — porównanie dwóch tekstów
- Port (uvicorn): w kodzie `uvicorn.run(..., port=8050)`
- Docker mapping: `docker-compose.yml` ma `8050:8006` — UWAGA: mismatch (internal port w compose 8006, a w kodzie 8050)
- Gdzie edytować: `services/embeddings-service/main.py`

### 8) RAG Service
- Ścieżka: `services/rag-service/main.py`
- Cel: retrieval-augmented generation — wyszukiwanie semantyczne w pgvector i agregacja wyników
- Key endpoints:
  - `GET /` — info
  - `GET /health` — sprawdza DB i Embeddings service
  - `POST /search` — przyjmuje `categorizer_id` i `query_text`, zwraca podobne próbki
  - `GET /stats/{categorizer_id}` — placeholder statystyk
- Port (uvicorn): w kodzie `uvicorn.run(..., port=8070)`
- Docker mapping: `docker-compose.yml` ma `8070:8007` — UWAGA: mismatch
- Gdzie edytować: `services/rag-service/main.py`

### 9) Evaluator
- Ścieżka: `services/evaluator/main.py`, `services/evaluator/quality_scorer.py`
- Cel: scoring jakości próbek treningowych, background worker do przeliczania ocen i pipeline curation
- Key endpoints:
  - `GET /health` — status serwisu i background worker
  - `POST /score_sample` — ręczne ocenienie próbki
  - `POST /score_batch` — ocena batcha
  - `GET /curation_status/{categorizer_id}` — status curation
  - `POST /run_curation` — ręczne uruchomienie curation pipeline
- Port: `docker-compose.yml` mapuje `8060:8060` — w kodzie service ma FastAPI z lifespan managerem (uruchomienie przez uvicorn powinno użyć portu 8060)
- Gdzie edytować: `services/evaluator/*`

### 10) Dashboards
- Admin: `services/dashboard-admin/main.py` — front-end (Jinja2) do zarządzania (port 8080 w kodzie), korzysta z `ORCHESTRATOR_URL`.
- HIL Dashboard: `services/dashboard-hil/main.py` — interfejs do przeglądu kolejki HIL (port 8081 w kodzie).
- Te aplikacje renderują szablony z `templates/` i statyczne pliki w `static/`.

### 11) Postgres / Redis
- Postgres: `services/postgres` (Dockerfile + `init.sql`) — baza danych; `docker-compose` expose `5432:5432`.
- Redis: konfiguracja w `docker-compose.yml` (hasło w `config/secrets.yaml` przykładowo)

---

## Zmienność portów / niespójności (lista do weryfikacji)

W kilku miejscach kod ustawia port uruchomieniowy (uvicorn.run) inny niż ten, który jest wystawiony w `docker-compose.yml` (warto ujednolicić):

- `services/xgboost-layer/main.py` — uvicorn port 8020; `docker-compose` mapuje `8020:8003` → mismatch: sprawdź i zaktualizuj albo `main.py`, albo `docker-compose.yml`.
- `services/llm-layer/main.py` — uvicorn port 8030; `docker-compose` mapuje `8030:8004` → mismatch.
- `services/embeddings-service/main.py` — uvicorn port 8050; `docker-compose` mapuje `8050:8006` → mismatch.
- `services/rag-service/main.py` — uvicorn port 8070; `docker-compose` mapuje `8070:8007` → mismatch.

Rekomendacja: ustal jeden sposób (najlepiej: porty wewnętrzne w serwisach ustaw na standardowe wartości i użyj ENV w docker-compose do ich nadpisania) i zrób commit konfiguracji.

---

## Gdzie edytować

- Zmiany konfiguracyjne globalne: `config/config.yaml` (orchestrator, thresholds, timeouts)
- Zmiany środowiskowe lub secrets: `config/secrets.yaml` (nie commituj prawdziwych sekretów)
- Zmiana endpointów / logiki serwisu: `services/<service>/main.py` (tam jest większość logiki HTTP)
- Docker/build: `services/<service>/Dockerfile` oraz `docker-compose.yml`
- Modele i dane trwałe: `volumes/models`, `volumes/postgres`, etc. (zdefiniowane w `docker-compose.yml`)

---

## Szybkie wskazówki developerskie

- Uruchamianie jednego serwisu lokalnie: `python services/<service>/main.py` (sprawdź `if __name__ == "__main__"`).
- Aby debugować integracyjnie: uruchom `orchestrator + postgres + redis + tags-layer` i wykonaj prostą ścieżkę klasyfikacji.
- Jeśli by naprawić mapping portów: zmień wartość w `docker-compose.yml` lub w `main.py` (bardziej przyszłościowe: przenieś port do ENV var i użyj go zarówno w `docker-compose` jak i w `uvicorn.run(host, port=int(os.getenv("PORT", <domyślna>)))`).

---

## Checklist — co zrobić najpierw (propozycja)

1. Ujednolić porty między `docker-compose.yml` i `main.py` (przynajmniej dla: xgboost, llm, embeddings, rag)
2. Dodać env-var `PORT` do każdego serwisu i używać go w `uvicorn.run(...)`
3. Przegląd `config/config.yaml` i zastanowienie się nad przeniesieniem URL warstw do ENV
4. Dodać prosty test integracyjny uruchamiający minimalny scenariusz

---

Jeśli chcesz, mogę teraz:
- zaktualizować `programmingReferences.md` o wyciągnięte przykładowe payloady dla endpointów,
- przygotować PR z proponowaną ujednoliconą konfiguracją portów (bez zmian w działającym kodzie — najpierw proponuję zmiany w `docker-compose.yml` i dodanie ENV),
- albo wygenerować skrypt do szybkiego sanity-checku portów (sprawdza zgodność `docker-compose.yml` z `main.py`).

Powiedz, co chcesz żebym zrobił dalej.

---

## Aktualna struktura katalogów i plików (kod)

Poniżej znajduje się zaktualizowane drzewo katalogów i plików związanych z kodem w repozytorium (lista wygenerowana automatycznie z repo). Jeśli czegoś brakuje, daj znać — dopiszę.

- docker-compose.yml
- generate_docs.py
- README.md
- programmingReferences.md
- config/
  - config.yaml
  - secrets.yaml.example

- services/
  - api-gateway/
    - main.py
    - Dockerfile
    - requirements.txt
    - .dockerignore
    - README.md

  - embeddings-service/
    - main.py
    - Dockerfile
    - requirements.txt
    - .dockerignore

  - evaluator/
    - main.py
    - quality_scorer.py
    - quality_scorer_hybrid.py
    - config_loader.py
    - models/
      - database.py
    - Dockerfile
    - requirements.txt
    - README.md
    - .dockerignore

  - hil-layer/
    - main.py
    - webhooks.py
    - models/
      - webhooks.py
    - Dockerfile
    - Dockerfile.bak
    - requirements.txt
    - README.md
    - .dockerignore

  - llm-layer/
    - main.py
    - Dockerfile
    - requirements.txt
    - README.md
    - .dockerignore

  - orchestrator/
    - main.py
    - persistence.py
    - config_loader.py
    - models/
      - database.py
    - api/
      - __init__.py
      - training.py
      - management.py
      - classification.py
      - analytics.py
      - rag.py
    - Dockerfile
    - requirements.txt
    - README.md
    - .dockerignore

  - rag-service/
    - main.py
    - Dockerfile
    - requirements.txt
    - .dockerignore

  - tags-layer/
    - main.py
    - Dockerfile
    - requirements.txt
    - README.md
    - .dockerignore

  - xgboost-layer/
    - main.py
    - Dockerfile
    - requirements.txt
    - README.md
    - .dockerignore

  - dashboard-admin/
    - main.py
    - Dockerfile
    - config_loader.py
    - requirements.txt
    - .dockerignore
    - templates/
      - index.html

  - dashboard-hil/
    - main.py
    - Dockerfile
    - config_loader.py
    - requirements.txt
    - .dockerignore
    - templates/
      - hil_queue.html

  - postgres/
    - Dockerfile
    - init.sql

- volumes/
  - postgres/
    - pg_hba.conf
    - pg_ident.conf
    - postgresql.conf
    - postgresql.auto.conf
  - redis/
    - appendonlydir/
      - appendonly.aof.manifest
      - appendonly.aof.1.incr.aof
      - appendonly.aof.1.base.rdb

---

Jeśli chcesz, mogę teraz z:
- wygenerować z tego drzewa plik JSON/CSV do szybkiego przeszukiwania,
- dodać do `programmingReferences.md` krótkie przykłady request/response dla najważniejszych endpointów (HIL, Orchestrator, Tags, XGBoost, LLM, RAG),
- lub od razu utworzyć prosty skrypt sanity-check, który porówna porty zadeklarowane w `docker-compose.yml` z wartościami `uvicorn.run(..., port=...)` znalezionymi w `services/*/main.py`.

Które działanie preferujesz? (podaj numer lub opis)
