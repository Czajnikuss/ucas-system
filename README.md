# UCAS - Universal Classification & Analysis System

UCAS to kaskadowy system klasyfikacji tekstów oparty na architekturze mikroserwisów. Zaprojektowany do przetwarzania zapytań systemowych (np. zgłoszeń Helpdesk) z wykorzystaniem wielu warstw decyzyjnych, od szybkich reguł, przez modele ML, aż po zaawansowane modele LLM ze wsparciem RAG.

## 🏗 Architektura

System składa się z niezależnych kontenerów Dockerowych komunikujących się przez REST API:

* **API Gateway (`:8000`)**: Główny punkt wejścia. Trasuje żądania do Orchestratora.
* **Orchestrator (`:8001`)**: Mózg kaskady. Zarządza przepływem żądań (Tags -> XGBoost -> LLM), zapisuje historię w bazie PostgreSQL i obsługuje logikę persistence (odtwarzanie modeli po restarcie).
* **Tags Layer (`:8010`)**: Najszybsza warstwa oparta na słowach kluczowych i wyrażeniach regularnych.
* **XGBoost Layer (`:8020`)**: Warstwa ML. Używa TF-IDF i algorytmu XGBoost do szybkiej klasyfikacji wzorców.
* **LLM Layer (`:8030`)**: Warstwa rozumienia języka naturalnego (Ollama). Przetwarza skomplikowane przypadki, korzystając z profesjonalnego polskiego promptu i kontekstu RAG.
* **RAG Service (`:8070`)**: Baza wektorowa (`pgvector`) dostarczająca kontekst z historycznych przykładów do warstwy LLM.
* **Embeddings Service (`:8050`)**: Lokalny model transformatorowy generujący wektory (osadzenia) dla RAG i Evaluatora (obsługuje paczkowanie zapytań).
* **Evaluator (`:8060`)**: Worker w tle. Analizuje jakość danych treningowych obliczając odległość kosinusową (`numpy`) próbek od centroidu (środka ciężkości) ich klasy. Automatycznie eliminuje szum.
* **PostgreSQL**: Baza danych (modele, historia klasyfikacji, pełne prompty LLM, dane treningowe).
* **Dashboard UI (`:8501`)**: Interfejs zarządzania (Streamlit).

## 🚀 Kluczowe Funkcjonalności

1.  **Kaskada Decyzyjna (Cascade)**: System próbuje sklasyfikować tekst najtańszą i najszybszą metodą. Jeśli Tags i XGBoost zwrócą niską pewność (Confidence), żądanie trafia do LLM.
2.  **Zarządzanie Jakością (Evaluator)**: Przeliczanie jakości wektorowej próbek w locie. Próbki poniżej zdefiniowanego progu są archiwizowane, co chroni model przed zjawiskiem *Data Poisoning*.
3.  **Management Dashboard (UI)**:
    * **Zarządzanie modelami**: Podgląd i usuwanie kategoryzatorów.
    * **Edytor Danych**: Ręczna modyfikacja, import z plików CSV (Tryby Overwrite / Append) oraz natychmiastowe przeliczanie całego potoku kaskady.
    * **Test API**: Interaktywne testowanie strategii (`cascade`, `llm`, `xgboost`, `tags`) z pełnym zrzutem JSON i podglądem wygenerowanego Promptu LLM z wstrzykniętym RAG.
    * **Statystyki**: Analiza czasu procesowania, dystrybucji warstw i przegląd ostatnich 50 zapytań prosto z bazy danych.

## 🛠 Wymagania

* Docker & Docker Compose (V2)
* Powershell (do skryptów testowych)
* Minimum 8GB RAM (Zalecane 16GB dla modeli LLM ładowanych do pamięci)

## ⚙️ Uruchomienie

1. Klonowanie repozytorium i uruchomienie środowiska:
```powershell
docker compose up -d

2. Pierwszy trening (przykład przez skrypt lub z UI):

PowerShell

.\test_xgb_800.ps1

3. Dostęp do usług:

Management UI: http://localhost:8501

API Gateway: http://localhost:8000

📡 API Endpoints (Gateway)
POST /classify - Główny endpoint klasyfikujący. Opcje strategii: cascade, fastest, all, llm, xgboost, tags. Obsługuje flagę return_prompt dla trybu debugowania.

POST /train - Buduje lub nadpisuje kategoryzator we wszystkich warstwach.

GET /categorizers - Zwraca listę załadowanych modeli.

DELETE /categorizers/{id} - Kasuje model z pamięci i bazy.

🧠 Mechanika Jakości Danych (Quality Scorer)
Evaluator działa na podstawie logiki wektorowej:

Pobiera do 1000 aktywnych próbek referencyjnych dla danej kategorii.

Odpytuje Embeddings Service o paczkę wektorów.

Wylicza Centroid (średni wektor w przestrzeni).

Próbki oceniane są na podstawie odległości od centroidu. Próg odcięcia tła (baseline) dla Sentence Transformers to standardowo 0.35.

Wynik jest normalizowany do przedziału [0.0, 1.0]. W przypadku awarii API wektorowego działa algorytm heurystyczny zabezpieczający kolejkę.