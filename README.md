# UCAS System - AI-Driven Citizen Feedback Analysis

Complete microservices system for real-time classification and human-in-the-loop review of citizen feedback.

## 🏗️ Architecture

```
┌─────────────────┐
│   Categorizer   │ (AI Classification)
│    :8001        │
└────────┬────────┘
         │ (Escalate)
         ▼
┌─────────────────┐
│   HIL Layer     │ (Human Review)
│    :8040        │
└────────┬────────┘
         │ (Webhooks)
         ▼
┌─────────────────┐
│   External      │ (Client Systems)
│   Webhooks      │
└─────────────────┘
```

## 🚀 Quick Start

```bash
podman compose up -d
podman compose ps
podman compose logs -f hil-layer
```

## 📡 Main Services

| Service | Port | Purpose |
|---------|------|---------|
| **Categorizer** | 8001 | AI classification |
| **HIL Layer** | 8040 | Human review |
| **PostgreSQL** | 5432 | Data storage |

## 🔄 Data Flow

1. Classification Request → Categorizer
2. Low Confidence → Escalate to HIL
3. Human Review → HIL Layer
4. Webhook Event → External systems
5. Training Update → New samples

## 📚 API Documentation

- **Categorizer Swagger:** http://localhost:8001/swagger
- **HIL Swagger:** http://localhost:8040/swagger

## 🔌 Webhook Integration

```bash
curl -X POST "http://localhost:8040/webhooks/register?name=MySystem&url=https://myapi.com/webhook"
```

Webhook payload:
```json
{
  "event": "hil.review.pending",
  "review_id": "uuid",
  "categorizer_id": "cat-001",
  "text": "Citizen feedback",
  "suggested_category": "COMPLAINT",
  "suggested_confidence": 0.42
}
```

## 📊 Database

Schema automatically created via `init.sql`:
- Categorizers & configurations
- Training samples with embeddings
- Classifications & cascade
- HIL reviews & feedback
- Webhook endpoints & history

## 🧪 Testing

```bash
curl http://localhost:8040/health
curl http://localhost:8040/webhooks
```

## 📦 Development

```bash
podman compose build
podman compose logs -f
podman compose down
podman volume prune
```

---
**Status:** Production Ready (v0.1)  
**Last Updated:** Nov 2025

---
## Rozszerzona dokumentacja i inwentaryzacja

Dodano plik `programmingReferences.md` z pełną inwentaryzacją projektu: per-service lista plików, kluczowe endpointy, zmienne środowiskowe, miejsca w kodzie, gdzie zmieniać porty i ustawienia oraz lista znanych niespójności (np. mapping portów w `docker-compose.yml` vs porty w `main.py`).

Propozycja dalszych kroków:
- Przejrzeć `programmingReferences.md` i skorygować niespójne porty (jednorodność: albo konfig w kodzie, albo w docker-compose/env).
- Dodać testy integracyjne uruchamiające minimalny zestaw serwisów (orchestrator + postgres + redis + tags) by zweryfikować bazowe scenariusze.

Plik `programmingReferences.md` znajduje się w katalogu root repo i zawiera szczegóły developerskie — sprawdź go przed edycją konfiguracji.

---

## Wymagane pliki lokalne i jak je utworzyć

Niektóre pliki nie są commitowane (albo są generowane lokalnie) i muszą być utworzone przed uruchomieniem systemu. Poniżej krótkie instrukcje tworzenia najważniejszych z nich:

- `config/secrets.yaml` — skopiuj przykładowy plik i wypełnij wartości:

```powershell
Copy-Item -Path config/secrets.yaml.example -Destination config/secrets.yaml
# Edytuj config/secrets.yaml i ustaw hasła/URL-e
notepad config\secrets.yaml
```

- `volumes/ollama/id_ed25519` + `id_ed25519.pub` — klucz prywatny/publiczny używany przez Ollama (jeśli wymagane):

```powershell
ssh-keygen -t ed25519 -f .\volumes\ollama\id_ed25519 -N ""
```

- Pliki inicjalizacyjne Postgres (`volumes/postgres/*`) — zwykle dostarczone w repo; jeśli nie, skopiuj szablony lub wygeneruj plik `init.sql` w `services/postgres/`.

- Plik `docker-compose.yml` — główny plik orkiestracji; jeśli tworzyłeś kopie zapasowe, zachowaj je lokalnie, ale upewnij się, że `docker-compose.yml` zawiera właściwe mappingi portów i ścieżki do wolumenów.

Krótki checklist przed uruchomieniem:
- Upewnij się, że `config/secrets.yaml` istnieje i nie zawiera placeholderów.
- Upewnij się, że klucze w `volumes/ollama/` są ustawione jeśli używasz Ollama.
- Sprawdź `docker-compose.yml` pod kątem portów i wolumenów.

Jeśli chcesz, mogę automatycznie utworzyć te pliki (np. skopiować `secrets.yaml.example` → `config/secrets.yaml` i wygenerować klucze), albo dodać przykładowy skrypt `scripts/setup_local.ps1` do repo.
