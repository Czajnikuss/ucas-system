# Orchestrator Service

## Overview
Orchestrator jest centralnym komponentem systemu UCAS, odpowiedzialnym za:
- Koordynację procesu klasyfikacji
- Zarządzanie modelami i danymi treningowymi
- Komunikację między warstwami
- Persystencję danych w PostgreSQL

## Funkcjonalności

### Klasyfikacja
- Strategia kaskadowa (cascade)
- Równoległa klasyfikacja (all)
- Szybka klasyfikacja (fastest)
- Human-in-the-Loop (HIL) dla niepewnych przypadków

### Zarządzanie Modelami
- Inicjalizacja i trening kategoryzatorów
- Przechowywanie stanu modeli
- Automatyczna regeneracja embedingów
- Przywracanie stanu po restarcie

### Persist encja
- PostgreSQL dla danych treningowych i historii
- Zapis stanu modeli na dysku
- Automatyczne przywracanie po restarcie

## API Endpoints

### Klasyfikatory
- `POST /train` - Tworzenie i trening nowego kategoryzatora
- `GET /categorizers` - Lista wszystkich kategoryzatorów
- `GET /categorizers/{id}` - Szczegóły kategoryzatora
- `GET /categorizers/{id}/history` - Historia klasyfikacji

### Klasyfikacja
- `POST /classify` - Klasyfikacja tekstu
- `POST /search_similar` - Wyszukiwanie podobnych próbek (RAG)

### System
- `GET /health` - Stan systemu i komponentów
- `GET /swagger` - Dokumentacja OpenAPI

## Konfiguracja
Serwis konfigurowany przez zmienne środowiskowe:
- Adresy pozostałych serwisów (TAGS_LAYER, XGBOOST_LAYER, LLM_LAYER)
- Parametry bazy danych
- Progi pewności dla każdej warstwy

## Progi Pewności (domyślne)
- Tags Layer: 0.7
- XGBoost Layer: 0.7
- LLM Layer: 0.8

## Strategie Klasyfikacji

### Cascade (domyślna)
1. Tags Layer (szybkie dopasowanie)
2. XGBoost Layer (ML)
3. LLM Layer (reasoning)
4. HIL Layer (human review)

### All (równoległa)
- Wszystkie warstwy równolegle
- Wybór najlepszego wyniku

### Fastest
- Pierwsza pozytywna odpowiedź
- Optymalizacja czasu odpowiedzi

## Dokumentacja API
Swagger UI dostępne pod: http://localhost:8001/swagger

## Przykłady Użycia

### Trenowanie Kategoryzatora
```bash
curl -X POST http://localhost:8001/train \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Categorizer",
    "description": "Test instance",
    "training_data": [
      {"text": "Sample text", "category": "Category1"}
    ],
    "layers": ["tags", "xgboost", "llm"],
    "fallback_category": "Other"
  }'
```

### Klasyfikacja
```bash
curl -X POST http://localhost:8001/classify \
  -H "Content-Type: application/json" \
  -d '{
    "categorizer_id": "test-categorizer",
    "text": "Text to classify",
    "strategy": "cascade"
  }'
```