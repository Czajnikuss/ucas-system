# Tags Layer Service

## Overview
Tags Layer to szybka warstwa klasyfikacji oparta na słowach kluczowych, zoptymalizowana dla języka polskiego. Wykorzystuje różne metryki do identyfikacji najważniejszych słów kluczowych dla każdej kategorii.

## Kluczowe Funkcje

### Obsługa Języka Polskiego
- Normalizacja znaków diakrytycznych (ą→a, ę→e, etc.)
- Lista stop words dla języka polskiego
- Pełne wsparcie dla UTF-8

### Ekstrakcja Słów Kluczowych
- TF-IDF dla ważności słów
- Analiza dyskryminacyjna
- N-gramy (1-2 słowa)
- Metryki częstotliwości

### Klasyfikacja
- Dokładne dopasowanie słów
- Wsparcie dla wyrażeń regularnych
- Normalizacja tekstu
- Scoring wielokryterialny

## API Endpoints

### System
- `GET /` - Informacje o serwisie
- `GET /health` - Stan serwisu
- `GET /swagger` - Dokumentacja OpenAPI

### Klasyfikacja
- `POST /train` - Trening na danych
- `POST /classify` - Klasyfikacja tekstu
- `GET /categorizers/{id}/keywords` - Lista słów kluczowych
- `POST /restore` - Przywrócenie stanu kategoryzatora

## Konfiguracja Treningu

### Parametry
- `max_keywords`: Maksymalna liczba słów na kategorię (default: 10)
- `min_keyword_length`: Minimalna długość słowa (default: 3)
- `normalize_text`: Normalizacja polskich znaków (default: true)
- `use_polish_stopwords`: Użycie stop words (default: true)

### Scoring Słów
- 50% - TF-IDF score
- 30% - Unikalność kategorialna
- 20% - Częstotliwość globalna

## Przykłady Użycia

### Trening
```bash
curl -X POST http://localhost:8010/train \
  -H "Content-Type: application/json" \
  -d '{
    "categorizer_id": "test-tags",
    "training_data": [
      {"text": "Produkt uszkodzony", "category": "Problem"},
      {"text": "Świetna obsługa", "category": "Pochwała"}
    ],
    "max_keywords": 10,
    "normalize_text": true
  }'
```

### Klasyfikacja
```bash
curl -X POST http://localhost:8010/classify \
  -H "Content-Type: application/json" \
  -d '{
    "categorizer_id": "test-tags",
    "text": "Ten produkt jest wadliwy"
  }'
```

## Dokumentacja API
Swagger UI dostępne pod: http://localhost:8010/swagger

## Monitorowanie
- Stan serwisu: http://localhost:8010/health
- Statystyki kategoryzatora: GET /categorizers/{id}/keywords

## Optymalizacja Wydajności
- Cache słów kluczowych w pamięci
- Precompiled regex patterns
- Szybkie dopasowania exact-match
- Równoległa analiza kategorii