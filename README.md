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
git clone https://github.com/Czajnikuss/ucas-system.git
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
**Benchmark:** 80% cases resolved in <10ms via Tags layer

## 🔧 Configuration

### Layer-Specific Settings
```json
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
```


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

