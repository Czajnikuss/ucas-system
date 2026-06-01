# UCAS — Kalkulator ROI + szablon Case Study (DRAFT)

> Dwa narzędzia sprzedażowe w jednym pliku:
> 1. **Kalkulator ROI** — wypełnij liczbami klienta, pokaż oszczędność.
> 2. **Szablon Case Study** — uzupełnij realnymi wynikami z pierwszego wdrożenia.
> Status: **DRAFT** — pola `[w nawiasach]` do uzupełnienia. Wymaga akceptacji właściciela.

---

## 1. Kalkulator ROI (prosty model)

**Dane wejściowe (od klienta):**
- A = liczba zgłoszeń/maili do ręcznej kategoryzacji miesięcznie: `[np. 4 000]`
- B = średni czas ręcznej kategoryzacji jednego zgłoszenia (min): `[np. 1,5]`
- C = koszt godziny pracy agenta (PLN): `[np. 45]`
- D = udział zgłoszeń, które UCAS sklasyfikuje automatycznie: `[np. 0,85]`

**Wyliczenie:**
```
Czas ręczny dziś (h/mies)        = A × B / 60
Koszt ręczny dziś (PLN/mies)     = (A × B / 60) × C
Zaoszczędzony czas (h/mies)      = (A × D × B) / 60
Oszczędność (PLN/mies)           = ((A × D × B) / 60) × C
```

**Przykład (A=4000, B=1,5, C=45, D=0,85):**
- Koszt ręczny dziś: (4000 × 1,5 / 60) × 45 = 100 h × 45 = **4 500 PLN/mies**
- Oszczędność po wdrożeniu: (4000 × 0,85 × 1,5 / 60) × 45 = 85 h × 45 = **~3 825 PLN/mies**
- Przy koszcie usługi/licencji rzędu 1 500–3 000 PLN/mies → **dodatnie ROI od 1. miesiąca**.

> Dodatkowe, trudniej wyceniane korzyści: krótszy czas reakcji, mniej błędnego routingu,
> stały ślad audytowy, brak wycieku danych (on-prem).

---

## 2. Szablon Case Study

### [Nazwa klienta / branża]
**Okres:** `[MM.RRRR – MM.RRRR]` · **Wdrożenie przez:** `[partner / integrator]`

**Wyzwanie**
`[np. 4 000 zgłoszeń/mies kategoryzowanych ręcznie; długi czas reakcji; błędny routing do działów.]`

**Rozwiązanie (UCAS)**
- Kategoryzator: `[liczba kategorii]`, warstwy: `[tags / xgboost / llm]`.
- Tryb: `[on-prem / współdzielony]`; dane `[nie opuszczają / opuszczają]` infrastrukturę klienta.
- Human-in-the-Loop dla przypadków poniżej progu pewności.

**Wyniki (liczby)**
| Metryka | Przed | Po |
|---|---|---|
| Automatyzacja kategoryzacji | `[%]` | `[%]` |
| Średni czas obsługi zgłoszenia | `[min]` | `[min]` |
| Udział trafień warstw tanich (tags/xgboost) | — | `[%]` |
| Oszczędność miesięczna | — | `[PLN]` |

**Cytat klienta**
> „`[1–2 zdania o efekcie]`" — `[imię, rola]`

**Czego użyć w rozmowie z kolejnym klientem**
- Liczba automatyzacji + oszczędność jako kotwica wartości.
- Argument prywatności (on-prem), jeśli klient jest regulowany.

---

### Jak zbierzemy liczby z systemu
- `GET /categorizers/{id}/stats` → `method_distribution` (udział warstw) + `average_processing_time_ms`.
- `GET /categorizers/{id}/history` → próbki klasyfikacji do jakościowej ilustracji.
- Panel **Statystyki & Historia** (http://localhost:8080) → te same dane wizualnie.
