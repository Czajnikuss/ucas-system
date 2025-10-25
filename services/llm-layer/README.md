# LLM Layer Service

## Overview
LLM Layer to warstwa klasyfikacji wykorzystująca modele językowe. Wspiera klasyfikację kontekstową, wykrywanie przypadków spoza zakresu (fallback) i dynamiczne przykłady (RAG).

## Kluczowe Funkcje

### Modele i Wydajność
- Automatyczna detekcja GPU
- Dynamiczna konfiguracja warstw
- Wsparcie dla różnych modeli:
  - phi3:mini (domyślny)
  - gemma:2b
  - llama3.1:8b
  - mistral:7b

### RAG (Retrieval Augmented Generation)
- Dynamiczne wyszukiwanie podobnych przykładów
- Integracja z bazą treningową
- Optymalizacja promptów

### Klasyfikacja
- Few-shot learning
- Kategoria fallback dla przypadków spoza zakresu
- Szczegółowe wyjaśnienia decyzji
- Scoring pewności

## API Endpoints

### System
- `GET /` - Informacje o serwisie
- `GET /health` - Stan systemu i GPU
- `GET /swagger` - Dokumentacja OpenAPI

### Klasyfikacja
- `POST /train` - Trening kategoryzatora
- `POST /classify` - Klasyfikacja tekstu
- `GET /categorizers/{id}/info` - Informacje o kategoryzatorze

## Konfiguracja

### GPU
```json
{
  "gpu_config": {
    "num_gpu": 1,
    "gpu_memory_fraction": 0.8
  }
}
```

### Model
```json
{
  "model": "phi3:mini",
  "fallback_category": "Inne"
}
```

## Przykłady Użycia

### Trening
```bash
curl -X POST http://localhost:8030/train \
  -H "Content-Type: application/json" \
  -d '{
    "categorizer_id": "test-llm",
    "training_data": [
      {"text": "Produkt wadliwy", "category": "Problem"},
      {"text": "Świetna obsługa", "category": "Pochwała"}
    ],
    "model": "phi3:mini",
    "fallback_category": "Inne"
  }'
```

### Klasyfikacja
```bash
curl -X POST http://localhost:8030/classify \
  -H "Content-Type: application/json" \
  -d '{
    "categorizer_id": "test-llm",
    "text": "Dziękuję za pomoc"
  }'
```

## Dokumentacja API
Swagger UI dostępne pod: http://localhost:8030/swagger

## Monitoring
- Stan serwisu: http://localhost:8030/health
- Informacje o GPU
- Statystyki modeli

## Format Odpowiedzi
```json
{
  "category": "Pochwała",
  "confidence": 0.85,
  "reasoning": "Pozytywny feedback dotyczący obsługi",
  "method": "llm",
  "gpu_used": true,
  "is_fallback": false
}
```

## Obsługa Błędów
- Timeout: 60s dla klasyfikacji
- Automatyczne pobieranie modeli
- Fallback na CPU przy problemach z GPU
- Obsługa przypadków brzegowych

## Optymalizacja
- Buforowanie modeli w pamięci
- Dynamiczny dobór liczby warstw GPU
- Batching dla wielu zapytań
- Automatyczny dobór przykładów