# UCAS — Universal Classification & Analysis System

> Production-ready, multi-layer text classification system. Combines fast rules, XGBoost and an LLM reasoning layer.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-green.svg)](https://www.python.org/)

## Contents

- Overview
- Architecture
- Quick start
- Examples (train, classify)
- Configuration
- Project structure
- Development & tests
- Contributing
- License
- Polish translation (PL)

---

## Overview

UCAS (Universal Classification & Analysis System) is a modular system for text classification designed for production use. It uses a cascade approach:

- Tags layer — fast keyword matching
- XGBoost layer — machine learning classifier
- LLM layer — large language model for ambiguous cases

The cascade prefers speed and falls back to more expensive but more accurate layers when needed.

Key features:

- Multi-layer cascade with failover
- Out-of-scope / fallback detection
- UTF-8 multilingual support (tested with Polish)
- GPU auto-detect with CPU fallback
- Persistent models via Docker volumes

## Architecture

High-level components (example ports):

- `api-gateway` (8000) — HTTP gateway
- `orchestrator` (8001) — cascade logic, training & classification API
- `tags-layer` (8010) — keyword matching
- `xgboost-layer` (8020) — ML model server
- `llm-layer` (8030) — LLM service (e.g. Ollama)

Services are orchestrated using `docker compose` defined in the repository root.

## Quick start

Requirements:

- Docker Desktop 4.x+ (Windows)
- Minimum 8 GB RAM (16 GB recommended)
- ~10 GB disk for models

Clone and run:

```powershell
git clone https://github.com/yourusername/ucas-system.git
cd ucas-system
docker compose up -d
```

Check services:

```powershell
docker compose ps
```

Health endpoint example:

```powershell
curl http://localhost:8001/health
```

Note: initial model loading may take ~60s on first run.

## Examples

Train a simple classifier (POST /train):

```powershell
curl -X POST http://localhost:8001/train \
  -H "Content-Type: application/json" \
  -d '{
    "categorizer_id": "demo",
    "training_data": [
      {"text": "Product is broken", "category": "Quality"},
      {"text": "Delivery was late", "category": "Logistics"},
      {"text": "Support was helpful", "category": "Support"}
    ],
    "fallback_category": "Other"
  }'
```

Classify text (POST /classify):

```powershell
curl -X POST http://localhost:8001/classify \
  -H "Content-Type: application/json" \
  -d '{
    "categorizer_id": "demo",
    "text": "The product arrived damaged",
    "strategy": "cascade"
  }'
```

Example response:

```json
{
  "category": "Quality",
  "confidence": 1.0,
  "method": "tags",
  "processing_time_ms": 7.2,
  "is_fallback": false
}
```

## Classification strategies

- `cascade` — recommended: try tags → xgboost → llm
- `all` — execute all layers and return best result
- `fastest` — return the first successful result

## Configuration

Example configuration (e.g. `config/*.json`):

```json
{
  "tags_config": { "max_keywords": 5, "normalize_text": false },
  "xgboost_config": { "params": { "max_depth": 6, "n_estimators": 100 } },
  "llm_config": { "model": "phi3:mini", "gpu_config": { "num_gpu": -1 } }
}
```

Adjust values according to your environment. Config files live in `config/`.

## Project structure

Top-level folders:

```
ucas-system/
├─ services/
│  ├─ api-gateway/
│  ├─ orchestrator/
│  ├─ tags-layer/
│  ├─ xgboost-layer/
│  └─ llm-layer/
├─ volumes/
└─ docker-compose.yml
```

## Development & tests

Run tests example (orchestrator):

```powershell
docker compose exec orchestrator pytest tests/
```

Developer notes:

- Each service has a `requirements.txt` for Python dependencies
- Check `Dockerfile` files in `services/*` for ports and env vars

## Contributing

Please read `CONTRIBUTING.md` for contribution guidelines. We welcome issues, PRs and improvements — see the contributing document for a short checklist and branch/PR conventions.

## License

MIT License — see `LICENSE` file.

---

## Polish translation (PL)

Poniżej znajduje się przetłumaczona wersja README w języku polskim.

### Opis

UCAS to modularny system do klasyfikacji tekstu zaprojektowany do użycia w środowisku produkcyjnym. System wykorzystuje kaskadowe podejście: najpierw szybkie dopasowanie słów-kluczy (tags), następnie model XGBoost, a w razie potrzeby — model LLM do rozstrzygnięcia trudniejszych przypadków.

Główne zalety:

- Wielowarstwowa kaskada (szybko → dokładnie)
- Wykrywanie tekstów poza zakresem (fallback)
- Obsługa UTF-8 (testy z polskimi znakami)
- Automatyczne wykrywanie GPU z fallbackem na CPU
- Trwałość modeli w woluminach Docker (models/)

### Architektura

- `api-gateway` (port 8000) — brama API
- `orchestrator` (port 8001) — logika kaskady, punkt trenowania i klasyfikacji
- `tags-layer` (8010) — szybkie reguły/keyword matching
- `xgboost-layer` (8020) — klasyfikator ML
- `llm-layer` (8030) — rozumowanie LLM (np. Ollama)

Usługi uruchamiane są przez `docker compose` z pliku `docker-compose.yml`.

### Szybki start

Wymagania:

- Docker Desktop 4.x+
- Min. 8 GB RAM (16 GB rekomendowane)
- Min. 10 GB wolnego miejsca dyskowego (modele)

Klonowanie i uruchomienie:

```powershell
git clone https://github.com/yourusername/ucas-system.git
cd ucas-system
docker compose up -d
```

Sprawdź status usług:

```powershell
docker compose ps
```

Sprawdź health:

```powershell
curl http://localhost:8001/health
```

### Przykłady użycia

Trenowanie (POST /train) i klasyfikacja (POST /classify) — przykłady analogiczne do sekcji angielskiej.

---

If you'd like, I can also add an `env.example` file, a short PowerShell helper script in `scripts/` to run a single service locally, or a `CONTRIBUTING.md` in Polish as well. Let me know which you'd prefer next.
# UCAS — Universal Classification & Analysis System

> Produkcyjny, wielowarstwowy system klasyfikacji tekstu (PL). Łączy szybkie reguły, klasyfikator XGBoost i warstwę LLM.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-green.svg)](https://www.python.org/)

## Spis treści

- Opis
- Architektura
- Szybki start
- Przykłady użycia (trening, klasyfikacja)
- Konfiguracja
- Struktura projektu
- Rozwój i testy
- Licencja

## Opis

UCAS to modularny system do klasyfikacji tekstu, zaprojektowany do użycia w środowisku produkcyjnym. System wykorzystuje kaskadowe podejście: najpierw szybkie dopasowanie słów-kluczy (tags), następnie model XGBoost, a w razie potrzeby — model LLM do rozstrzygnięcia trudniejszych przypadków.

Główne zalety:

- Wielowarstwowa kaskada (szybko → dokładnie)
- Wykrywanie tekstów poza zakresem (fallback)
- Obsługa UTF-8 (testy z polskimi znakami)
- Automatyczne wykrywanie GPU z fallbackem na CPU
- Trwałość modeli w woluminach Docker (models/)

## Architektura

Schemat (upraszczony):

- `api-gateway` (port 8000) — brama API
- `orchestrator` (port 8001) — logika kaskady, punkt trenowania i klasyfikacji
- `tags-layer` (np. port 8010) — szybkie reguły/keyword matching
- `xgboost-layer` (np. port 8020) — klasyfikator ML
- `llm-layer` (np. port 8030) — rozumowanie LLM (np. Ollama)

Poszczególne serwisy uruchamiane są przez `docker compose` z pliku `docker-compose.yml` znajdującego się w katalogu głównym repozytorium.

## Szybki start

Wymagania:

- Docker Desktop 4.x+ (Windows)
- Min. 8 GB RAM (16 GB rekomendowane)
- Min. 10 GB wolnego miejsca dyskowego (modele)

Klonowanie repozytorium i uruchomienie:

```powershell
git clone https://github.com/yourusername/ucas-system.git
cd ucas-system
docker compose up -d
```

Sprawdź status usług:

```powershell
docker compose ps
```

Sprawdź prosty endpoint zdrowia (health):

```powershell
curl http://localhost:8001/health
```

Uwaga: przy pierwszym uruchomieniu inicjalizacja modeli może potrwać ~60s lub dłużej w zależności od środowiska.

## Przykłady użycia

1) Trenowanie prostego klasyfikatora (POST /train)

```powershell
curl -X POST http://localhost:8001/train \
  -H "Content-Type: application/json" \
  -d '{
    "categorizer_id": "demo",
    "training_data": [
      {"text": "Product is broken", "category": "Quality"},
      {"text": "Delivery was late", "category": "Logistics"},
      {"text": "Support was helpful", "category": "Support"}
    ],
    "fallback_category": "Other"
  }'
```

2) Klasyfikacja tekstu (POST /classify)

```powershell
curl -X POST http://localhost:8001/classify \
  -H "Content-Type: application/json" \
  -d '{
    "categorizer_id": "demo",
    "text": "The product arrived damaged",
    "strategy": "cascade"
  }'
```

Przykładowa odpowiedź JSON:

```json
{
  "category": "Quality",
  "confidence": 1.0,
  "method": "tags",
  "processing_time_ms": 7.2,
  "is_fallback": false
}
```

## Strategie klasyfikacji

- `cascade` (domyślna, zalecana) — kolejno: tags → xgboost → llm, zatrzymuje się przy pierwszym wystarczającym wyniku
- `all` — uruchamia wszystkie warstwy i zwraca najlepszy wynik
- `fastest` — zwraca pierwszy poprawny wynik

## Konfiguracja

Przykładowe ustawienia (np. `config/*.json`):

```json
{
  "tags_config": { "max_keywords": 5, "normalize_text": false },
  "xgboost_config": { "params": { "max_depth": 6, "n_estimators": 100 } },
  "llm_config": { "model": "phi3:mini", "gpu_config": { "num_gpu": -1 } }
}
```

Dostosuj wartości do swoich potrzeb. Pliki konfiguracyjne są w katalogu `config/`.

## Struktura projektu

Główne foldery i ich cele:

- `services/` — kod poszczególnych serwisów (api-gateway, orchestrator, tags-layer, xgboost-layer, llm-layer)
- `volumes/models/` — trwałe woluminy z zapisanymi modelami i konfiguracją
- `docker-compose.yml` — orkiestracja kontenerów

Przykładowa struktura:

```
ucas-system/
├─ services/
│  ├─ api-gateway/
│  ├─ orchestrator/
│  ├─ tags-layer/
│  ├─ xgboost-layer/
│  └─ llm-layer/
├─ volumes/
└─ docker-compose.yml
```

## Rozwój i testy

Uruchamianie testów (przykład dla `orchestrator`):

```powershell
docker compose exec orchestrator pytest tests/
```

Wskazówki deweloperskie:

- W plikach `services/*/requirements.txt` znajdują się zależności Python
- Każdy serwis ma własny `Dockerfile` — sprawdź porty i zmienne środowiskowe

## Licencja

Projekt udostępniony na licencji MIT — zobacz plik `LICENSE`.

## Podziękowania

- Ollama — lokalne uruchamianie LLM
- XGBoost — klasyfikator ML
- FastAPI — framework serwera HTTP

---

Jeśli chcesz, mogę dodatkowo przygotować: krótką sekcję „Contributing”, instrukcję `env.example` z wymaganymi zmiennymi środowiskowymi lub prosty skrypt do lokalnego uruchomienia pojedynczego serwisu.

*** End Patch# UCAS - Universal Classification & Analysis System

> 🚀 Production-ready multi-layer text classification system with AI reasoning

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-green.svg)](https://www.python.org/)

## 🎯 Overview

UCAS is an intelligent text classification system that combines three complementary approaches:
- **Tags Layer** - Lightning-fast keyword matching (6-8ms)
- **XGBoost Layer** - Machine learning classification (10-50ms)
- **LLM Layer** - AI reasoning with GPT-class models (3-5s)

### Key Features

✅ **Multi-layer Cascade** - Automatic failover from fast to accurate  
✅ **Out-of-scope Detection** - Configurable fallback categories  
✅ **Multilingual Support** - Full UTF-8, tested with Polish diacritics  
✅ **GPU Auto-config** - Automatic detection with CPU fallback  
✅ **Model Persistence** - Training data survives container rebuilds  
✅ **Production Ready** - Docker Compose, health checks, monitoring

## 🏗️ Architecture

┌─────────────────────────────────────────────────────────────┐
│ API Gateway (8000) │
└─────────────────────┬───────────────────────────────────────┘
│
┌─────────▼─────────┐
│ Orchestrator │ ← Cascade Logic
│ (8001) │
└──┬────────┬───────┘
│ │
┌───────▼────┐ │ ┌─────▼──────┐
│ Tags (8010)│ │ │ XGBoost │
│ ~8ms │ │ │ (8020) │
└────────────┘ │ │ ~30ms │
│ └────────────┘
┌─────▼─────┐
│ LLM (8030)│
│ ~5s       │
│ +Ollama   │
└───────────┘


## 🚀 Quick Start

### Prerequisites

- Docker Desktop 4.x+
- 8GB RAM minimum (16GB recommended)
- 10GB disk space (for models)

### Installation

Clone repository
git clone https://github.com/yourusername/ucas-system.git
cd ucas-system

Start all services
docker compose up -d

Wait for services to be ready (~60s for first run)
docker compose ps

Check health
curl http://localhost:8001/health


### First Classification

1. Train a classifier
curl -X POST http://localhost:8001/train
-H "Content-Type: application/json"
-d '{
"categorizer_id": "demo",
"training_data": [
{"text": "Product is broken", "category": "Quality"},
{"text": "Delivery was late", "category": "Logistics"},
{"text": "Support was helpful", "category": "Support"}
],
"fallback_category": "Other"
}'

2. Classify text
curl -X POST http://localhost:8001/classify
-H "Content-Type: application/json"
-d '{
"categorizer_id": "demo",
"text": "The product arrived damaged",
"strategy": "cascade"
}'


**Response:**

{
"category": "Quality",
"confidence": 1.0,
"method": "tags",
"processing_time_ms": 7.2,
"is_fallback": false
}


## 📖 Usage Guide

### Training a Classifier

import requests

training_request = {
"categorizer_id": "customer-feedback",
"training_data": [
{"text": "Product defective", "category": "Quality"},
{"text": "Shipment delayed", "category": "Logistics"},
{"text": "Agent was rude", "category": "Support"}
],
"layers": ["tags", "xgboost", "llm"],
"fallback_category": "Uncategorized"
}

response = requests.post(
"http://localhost:8001/train",
json=training_request
)
print(response.json())


### Classification Strategies

**1. Cascade (Recommended)**
result = requests.post(
"http://localhost:8001/classify",
json={
"categorizer_id": "customer-feedback",
"text": "Product broke after one day",
"strategy": "cascade"
}
).json()


**2. All Layers** - Run all, return best result  
**3. Fastest** - First successful response

## 📊 Performance

| Scenario | Layer | Latency | Accuracy |
|----------|-------|---------|----------|
| Clear keywords | Tags | 6-8ms | 100% |
| Similar patterns | XGBoost | 10-50ms | 85-95% |
| Ambiguous text | LLM | 3-5s | 90-98% |

**Benchmark:** 80% cases resolved in <10ms via Tags layer

## 🔧 Configuration

### Layer-Specific Settings

{
"tags_config": {
"max_keywords": 5,
"normalize_text": false
},
"xgboost_config": {
"params": {
"max_depth": 6,
"n_estimators": 100
}
},
"llm_config": {
"model": "phi3:mini",
"gpu_config": {
"num_gpu": -1
}
}
}



## 🛠️ Development

### Project Structure

ucas-system/
├── services/
│ ├── api-gateway/
│ ├── orchestrator/
│ ├── tags-layer/
│ ├── xgboost-layer/
│ └── llm-layer/
├── volumes/
├── docker-compose.yml
└── README.md


### Running Tests

docker compose exec orchestrator pytest tests/


## 📄 License

MIT License - see LICENSE file

## 🙏 Acknowledgments

- [Ollama](https://ollama.ai/) - Local LLM runtime
- [XGBoost](https://xgboost.readthedocs.io/) - ML framework
- [FastAPI](https://fastapi.tiangolo.com/) - Python API framework
- [Phi-3](https://huggingface.co/microsoft/Phi-3-mini-4k-instruct) - Microsoft LLM

---

**Built with ❤️ for production text classification**
#   u c a s - s y s t e m  
 