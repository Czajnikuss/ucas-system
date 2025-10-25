# API Gateway Service

## Overview
API Gateway służy jako główny punkt wejścia do systemu UCAS. Obsługuje routing żądań, autoryzację i walidację.

## Kluczowe funkcje
- Routing żądań do odpowiednich serwisów
- Obsługa uwierzytelniania i autoryzacji
- Monitorowanie stanu systemu
- Rate limiting i cache (Redis)
- Dokumentacja API (Swagger)

## API Endpoints

### System & Health
- `GET /` - Informacje o serwisie
- `GET /health` - Stan systemu i komponentów
- `GET /swagger` - Dokumentacja Swagger
- `GET /test/redis` - Test połączenia z Redis

### Categorizers API (v1)
- `POST /api/v1/categorizers/initialize` - Inicjalizacja nowego kategoryzatora
- `GET /api/v1/categorizers` - Lista wszystkich kategoryzatorów
- `GET /api/v1/categorizers/{id}/status` - Status kategoryzatora

## Konfiguracja
Serwis konfigurowany jest poprzez zmienne środowiskowe:
- `REDIS_HOST` (default: "redis")
- `REDIS_PASSWORD` (default: "ucas_redis_pass")
- `ORCHESTRATOR_URL` (default: "http://orchestrator:8001")

## Zależności
- Redis - cache i rate limiting
- Orchestrator - zarządzanie kategoryzatorami
- FastAPI - framework API
- httpx - asynchroniczny klient HTTP

## Dokumentacja API
Swagger UI dostępne pod adresem: http://localhost:8000/swagger

## Monitoring
Stan serwisu można monitorować poprzez endpoint `/health`, który zwraca:
- Status Redis
- Status Orchestratora
- Ogólny stan systemu

## Przykłady użycia

### Inicjalizacja kategoryzatora
```bash
curl -X POST http://localhost:8000/api/v1/categorizers/initialize \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Categorizer",
    "description": "Test categorizer instance",
    "config": {
      "language": "pl",
      "layers": ["tags", "xgboost", "llm"]
    }
  }'
```

### Sprawdzenie stanu
```bash
curl http://localhost:8000/health
```