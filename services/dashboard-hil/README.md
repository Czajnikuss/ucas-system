# Dashboard HIL (Human-in-the-Loop Review)

Lekki panel webowy (FastAPI + Jinja2) do przeglądania kolejki spraw eskalowanych do
weryfikacji przez człowieka. Wyświetla oczekujące zgłoszenia pobrane z `hil-layer` i
pozwala zatwierdzić właściwą kategorię.

> Serwis jest podłączony do `docker-compose.yml` (wcześniej istniał tylko w override i nie
> startował). Jest to jedyny dedykowany UI HIL — panel `dashboard-admin` go nie zawiera.

## Port
- **8081** (host i kontener): http://localhost:8081

## Endpointy
| Metoda | Ścieżka | Opis |
|---|---|---|
| GET | `/` | Kolejka oczekujących recenzji (HTML, `hil_queue.html`) |
| GET | `/health` | Status serwisu |

## Zmienne środowiskowe
| Zmienna | Domyślnie | Opis |
|---|---|---|
| `HIL_LAYER_URL` | `http://hil-layer:8040` | API warstwy HIL (`/pending`, `/review/{id}`) |

## Zależności
- **hil-layer** (8040) — źródło kolejki i zapis decyzji człowieka.

## Uruchomienie i test (Podman)
```powershell
podman compose up -d dashboard-hil
curl http://localhost:8081/health
start http://localhost:8081
```
