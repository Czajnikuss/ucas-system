# Kontekst projektu UCAS (Universal Classification & Analysis System)

## Ogólny opis projektu

UCAS to zaawansowany, wielowarstwowy system do klasyfikacji tekstu, zaprojektowany z myślą o środowiskach produkcyjnych. Jego głównym celem jest dostarczanie precyzyjnych i szybkich klasyfikacji poprzez zastosowanie architektury kaskadowej, która łączy w sobie różne technologie, od prostych reguł po zaawansowane modele językowe. System jest w pełni skonteneryzowany przy użyciu Dockera, co ułatwia jego wdrażanie i skalowanie.

Kluczowe cechy systemu:
- **Wielowarstwowa architektura kaskadowa** dla optymalnej wydajności i dokładności.
- **Monitorowanie w czasie rzeczywistym** kluczowych metryk systemu.
- **Ciągłe uczenie (Continuous Learning)** dzięki pętli informacji zwrotnej z udziałem człowieka (HIL).
- **Automatyczna ocena jakości** danych treningowych i modeli.
- **Elastyczność** w konfiguracji i doborze modeli.

## Architektura systemu

System składa się z kilku kluczowych mikroserwisów, które współpracują ze sobą w celu realizacji procesu klasyfikacji:

### Komponenty główne

- **API Gateway**: Główny punkt wejścia do systemu. Odpowiada za routing żądań, autoryzację, rate limiting oraz buforowanie (przy użyciu Redis). Udostępnia również dokumentację API (Swagger).

- **Orchestrator**: Centralny komponent systemu, który zarządza całym przepływem pracy. Odpowiada za tworzenie i trenowanie nowych kategoryzatorów, zarządzanie klasyfikacją tekstu w architekturze kaskadowej, dostarczanie analityk oraz obsługę zapytań RAG (Retrieval-Augmented Generation).

- **Evaluator**: Serwis odpowiedzialny za ocenę i utrzymanie wysokiej jakości danych treningowych. Automatycznie ocenia próbki, zarządza procesem kuracji zbiorów danych i optymalizuje je pod kątem trenowania modeli.

### Warstwy klasyfikacyjne

Kaskada klasyfikacyjna składa się z następujących warstw, uruchamianych sekwencyjnie:

1.  **Tags Layer**: Najszybsza warstwa, oparta na słowach kluczowych. Jest zoptymalizowana dla języka polskiego i wykorzystuje różne metryki (np. TF-IDF) do identyfikacji najważniejszych słów kluczowych dla każdej kategorii.

2.  **XGBoost Layer**: Warstwa oparta na uczeniu maszynowym. Wykorzystuje modele XGBoost w połączeniu z osadzeniami Word2Vec do klasyfikacji tekstu. Oferuje możliwość trenowania i wnioskowania w czasie rzeczywistym, zwracając predykcje wraz z oceną pewności.

3.  **LLM Layer**: Zaawansowana warstwa klasyfikacyjna wykorzystująca duże modele językowe (LLM). Wspiera klasyfikację kontekstową, dynamiczne wyszukiwanie przykładów (RAG) oraz wykrywanie przypadków spoza zdefiniowanego zakresu (fallback). Posiada wsparcie dla GPU w celu przyspieszenia obliczeń.

4.  **HIL Layer (Human-in-the-Loop)**: Warstwa interwencji człowieka. Zarządza procesem weryfikacji niepewnych lub niskiej jakości klasyfikacji przez ekspertów. Poprawione przez nich predykcje są wykorzystywane do ponownego trenowania modeli, co tworzy pętlę ciągłego doskonalenia.

## Testy E2E

Testy End-to-End dla całego systemu są uruchamiane za pomocą skryptu `test.ps1`, znajdującego się w głównym katalogu projektu.
