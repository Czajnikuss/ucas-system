# UCAS — Universal Classification & Analysis System

> **PL** poniżej · **EN** version [below ↓](#ucas--universal-classification--analysis-system-english)

---

UCAS to **samohostowany, kaskadowy silnik klasyfikacji tekstu** zbudowany w architekturze
mikroserwisów (FastAPI + Podman/Docker). Klasyfikuje zapytania systemowe (np. zgłoszenia Helpdesk,
maile, dokumenty) przepuszczając tekst przez kolejne, coraz droższe warstwy decyzyjne i
zatrzymując się na **pierwszej warstwie pewnej swojej odpowiedzi** — od szybkich reguł,
przez model ML, aż po LLM ze wsparciem RAG, a w ostateczności człowieka.

```
                     ┌──────────┐   confidence ≥ próg?
   tekst  ──────────▶│  TAGS    │──── tak ──▶ wynik
                     │  (regex) │
                     └────┬─────┘
                       nie│
                     ┌────▼─────┐
                     │ XGBoost  │──── tak ──▶ wynik
                     │  (ML)    │
                     └────┬─────┘
                       nie│
                     ┌────▼─────┐
                     │   LLM    │──── tak ──▶ wynik
                     │(Ollama+  │
                     │  RAG)    │
                     └────┬─────┘
                  niska   │ pewność
                     ┌────▼─────┐
                     │   HIL    │──▶ kolejka człowieka
                     │(człowiek)│    (+ webhooki)
                     └──────────┘
```

## 💡 Dlaczego UCAS (przewagi)

* **Optymalizacja kosztu** — ~90% ruchu obsługują tanie warstwy (regex + ML). Drogi LLM
  odpala się tylko dla trudnych przypadków. To realna oszczędność wobec „wołaj GPT do wszystkiego".
* **100% on-prem / prywatność (RODO)** — LLM działa lokalnie (Ollama). Dane nie opuszczają
  Twojej infrastruktury — kluczowe dla banków, ochrony zdrowia, kancelarii i sektora publicznego.
* **Human-in-the-Loop** — niepewne klasyfikacje trafiają do człowieka; poprawiona próbka
  wraca do danych treningowych. Pełny ślad audytowy + webhooki do integracji.
* **Aktywna kuracja jakości** — Evaluator liczy odległość próbek od centroidu klasy i
  archiwizuje szum, chroniąc model przed *data poisoning*.
* **Multi-tenant** — wiele niezależnych „kategoryzatorów" z jednego wdrożenia.
* **Dostrojony do języka polskiego** — profesjonalny polski prompt klasyfikujący.

## 🎯 Zastosowania

Routing zgłoszeń Helpdesk · triage maili · klasyfikacja dokumentów i reklamacji ·
moderacja treści · routing leadów / intencji · sortowanie zgłoszeń wg działu.

## 🏗 Architektura

Niezależne kontenery komunikujące się przez REST API:

| Serwis | Port | Rola |
|---|---|---|
| **API Gateway** | `8000` | Punkt wejścia. Dynamiczne proxy do Orchestratora. |
| **Orchestrator** | `8001` | Mózg kaskady. Przepływ żądań, persistence modeli, historia w PostgreSQL. |
| **Tags Layer** | `8010` | Najszybsza warstwa — słowa kluczowe i regex. |
| **XGBoost Layer** | `8020` | Warstwa ML — XGBoost na **pretrenowanych embeddingach** (transfer learning); fallback Word2Vec. |
| **LLM Layer** | `8030` | Rozumienie języka (Ollama) z polskim promptem i kontekstem RAG. |
| **HIL Layer** | `8040` | Human-in-the-Loop: kolejka review + webhooki. |
| **Embeddings Service** | `8050` | Lokalny model wielojęzyczny `paraphrase-multilingual-MiniLM-L12-v2` (384D) — cechy ML, RAG i Evaluator. |
| **Evaluator** | `8060` | Worker jakości danych (odległość kosinusowa od centroidu). |
| **RAG Service** | `8070` | Baza wektorowa (`pgvector`) — kontekst z historycznych przykładów dla LLM. |
| **PostgreSQL** | `5432` | Modele, historia klasyfikacji, prompty LLM, dane treningowe. |
| **Redis** | `6379` | Cache / warstwa Gateway. |
| **Ollama** | `11434` | Runtime lokalnych modeli LLM (domyślnie `phi3:mini`). |
| **Dashboard (Admin UI)** | `8080` | Zarządzanie (Streamlit). |
| **Dashboard HIL (Review UI)** | `8081` | Panel kolejki Human-in-the-Loop (FastAPI). |

## 🚀 Kluczowe funkcjonalności

1. **Kaskada decyzyjna** — strategie: `cascade`, `fastest`, `all`, `tags`, `xgboost`, `llm`.
   Flaga `return_prompt` zwraca pełny prompt LLM do debugowania.
2. **Zarządzanie jakością (Evaluator)** — przeliczanie jakości wektorowej próbek; próbki
   poniżej progu są archiwizowane (ochrona przed *data poisoning*).
3. **Management Dashboard (UI)** — zarządzanie modelami, edytor danych (import CSV w trybie
   Overwrite/Append), interaktywny Test API z podglądem promptu LLM + RAG, statystyki
   (czas procesowania, dystrybucja warstw, ostatnie zapytania).

## 🛠 Wymagania

* Podman (lub Docker) z Compose V2 — projekt jest uruchamiany na Podman
* PowerShell (do skryptów testowych w repo)
* Minimum 8 GB RAM (zalecane 16 GB dla modeli LLM)

## ⚙️ Uruchomienie

```powershell
# 1. Uruchom środowisko
podman compose up -d

# 2. Pierwszy trening (przykład przez skrypt)
.\scripts\test_xgb_800.ps1

# 3. Dostęp do usług:
#    Management UI : http://localhost:8080
#    API Gateway   : http://localhost:8000
#    Swagger (GW)  : http://localhost:8000/swagger
```

> 🎬 **Demo „pod klucz":** `demo/QUICKSTART.md` — skrypt `seed_demo.ps1` trenuje przykładowy kategoryzator helpdesk (8 kategorii, ~680 próbek) i pokazuje kaskadę w działaniu. Panel HIL: http://localhost:8081

## 📡 API (przez Gateway `:8000`)

| Metoda | Endpoint | Opis |
|---|---|---|
| `POST` | `/classify` | Klasyfikacja. Strategie: `cascade` (dom.), `fastest`, `all`, `tags`, `xgboost`, `llm`. Flaga `return_prompt`. |
| `POST` | `/train` | Buduje/aktualizuje kategoryzator we wszystkich warstwach. |
| `GET`  | `/categorizers` | Lista kategoryzatorów. |
| `GET`  | `/categorizers/{id}` | Szczegóły kategoryzatora. |
| `DELETE` | `/categorizers/{id}` | Usuwa kategoryzator (pamięć + baza). |
| `GET`  | `/categorizers/{id}/stats` | Statystyki (liczba zapytań, dystrybucja warstw, śr. czas). |
| `GET`  | `/categorizers/{id}/history` | Ostatnie klasyfikacje. |
| `GET`  | `/categorizers/{id}/export` | Eksport danych treningowych + konfiguracji. |
| `GET`  | `/health` | Status systemu i warstw. |

## 🧠 Mechanika jakości danych (Quality Scorer)

Evaluator działa na logice wektorowej:

1. Pobiera do 1000 aktywnych próbek referencyjnych danej kategorii.
2. Odpytuje Embeddings Service o paczkę wektorów.
3. Wylicza **centroid** (średni wektor klasy).
4. Ocenia próbki po odległości od centroidu; baseline odcięcia dla Sentence Transformers ≈ **0.35**.
5. Wynik normalizowany do `[0.0, 1.0]`. Przy awarii API wektorowego działa fallback heurystyczny.

---

# UCAS — Universal Classification & Analysis System (English)

UCAS is a **self-hosted, cascading text-classification engine** built as microservices
(FastAPI + Podman/Docker). It classifies system queries (Helpdesk tickets, emails, documents) by
routing text through progressively more expensive decision layers and **stopping at the first
layer that is confident** — from fast rules, through an ML model, to a RAG-augmented LLM, and
finally a human.

```
   text ──▶ TAGS (regex) ──hit──▶ result
              │ miss
              ▼
            XGBoost (ML) ──hit──▶ result
              │ miss
              ▼
            LLM (Ollama + RAG) ──hit──▶ result
              │ low confidence
              ▼
            HIL (human queue + webhooks)
```

## 💡 Why UCAS

* **Cost efficiency** — ~90% of traffic is handled by cheap layers (regex + ML); the
  expensive LLM only fires on hard cases. Real savings vs "call GPT for everything".
* **100% on-prem / privacy (GDPR)** — the LLM runs locally (Ollama); data never leaves your
  infrastructure. Decisive for banks, healthcare, law firms and the public sector.
* **Human-in-the-Loop** — uncertain predictions go to a human; the corrected sample flows
  back into training data. Full audit trail + webhooks.
* **Active data-quality curation** — the Evaluator scores samples by distance to the class
  centroid and archives noise, protecting the model from *data poisoning*.
* **Multi-tenant** — many independent "categorizers" from a single deployment.
* **Polish-language tuned** — professional Polish classification prompt out of the box
  (the cascade itself is language-agnostic).

## 🎯 Use cases

Helpdesk ticket routing · email triage · document & complaint classification · content
moderation · lead/intent routing · department-based sorting.

## 🏗 Architecture

| Service | Port | Role |
|---|---|---|
| **API Gateway** | `8000` | Entry point. Dynamic proxy to the Orchestrator. |
| **Orchestrator** | `8001` | Cascade brain. Request flow, model persistence, history in PostgreSQL. |
| **Tags Layer** | `8010` | Fastest layer — keywords & regex. |
| **XGBoost Layer** | `8020` | ML layer — XGBoost on **pretrained embeddings** (transfer learning); Word2Vec fallback. |
| **LLM Layer** | `8030` | NLU layer (Ollama) with Polish prompt and RAG context. |
| **HIL Layer** | `8040` | Human-in-the-Loop: review queue + webhooks. |
| **Embeddings Service** | `8050` | Local multilingual `paraphrase-multilingual-MiniLM-L12-v2` (384D) — ML features, RAG & Evaluator. |
| **Evaluator** | `8060` | Data-quality worker (cosine distance to centroid). |
| **RAG Service** | `8070` | Vector store (`pgvector`) — historical examples as LLM context. |
| **PostgreSQL** | `5432` | Models, classification history, LLM prompts, training data. |
| **Redis** | `6379` | Cache / Gateway layer. |
| **Ollama** | `11434` | Local LLM runtime (default `phi3:mini`). |
| **Dashboard (Admin UI)** | `8080` | Management UI (Streamlit). |
| **Dashboard HIL (Review UI)** | `8081` | Human-in-the-Loop review queue (FastAPI). |

## 🚀 Key features

1. **Decision cascade** — strategies: `cascade`, `fastest`, `all`, `tags`, `xgboost`, `llm`;
   `return_prompt` flag returns the full LLM prompt for debugging.
2. **Quality management (Evaluator)** — on-the-fly vector quality scoring; sub-threshold
   samples are archived (anti data-poisoning).
3. **Management Dashboard** — model management, data editor (CSV import Overwrite/Append),
   interactive API tester with LLM+RAG prompt preview, and statistics.

## 🛠 Requirements

* Podman (lub Docker) z Compose V2 — projekt jest uruchamiany na Podman
* PowerShell (for the test scripts in this repo)
* Minimum 8 GB RAM (16 GB recommended for LLM models)

## ⚙️ Quick start

```powershell
podman compose up -d            # 1. start the stack
.\scripts\test_xgb_800.ps1              # 2. first training (example)
# 3. Management UI : http://localhost:8080
#    API Gateway   : http://localhost:8000  (Swagger at /swagger)
```

> 🎬 **Turnkey demo:** see `demo/QUICKSTART.md` — `seed_demo.ps1` trains a sample helpdesk categorizer (8 categories, ~680 samples) and shows the cascade in action. HIL panel: http://localhost:8081

## 📡 API (via Gateway `:8000`)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/classify` | Classify. Strategies: `cascade` (default), `fastest`, `all`, `tags`, `xgboost`, `llm`. `return_prompt` flag. |
| `POST` | `/train` | Build/update a categorizer across all layers. |
| `GET`  | `/categorizers` | List categorizers. |
| `GET`  | `/categorizers/{id}` | Categorizer details. |
| `DELETE` | `/categorizers/{id}` | Delete a categorizer (memory + DB). |
| `GET`  | `/categorizers/{id}/stats` | Stats (request count, layer distribution, avg time). |
| `GET`  | `/categorizers/{id}/history` | Recent classifications. |
| `GET`  | `/categorizers/{id}/export` | Export training data + config. |
| `GET`  | `/health` | System & layer status. |

## 🧠 Data-quality mechanics (Quality Scorer)

1. Fetch up to 1000 active reference samples for the category.
2. Request a batch of vectors from the Embeddings Service.
3. Compute the **centroid** (mean class vector).
4. Score samples by distance to the centroid; Sentence-Transformers cutoff baseline ≈ **0.35**.
5. Score normalized to `[0.0, 1.0]`; a heuristic fallback runs if the vector API fails.
