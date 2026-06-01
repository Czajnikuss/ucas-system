# UCAS — One-pager dla partnerów (DRAFT do akceptacji)

> Materiał white-label. Integrator może podstawić własną markę w miejsca `[TWOJA MARKA]`.
> Status: **DRAFT** — przed wysyłką wymaga akceptacji właściciela.

---

## Czym jest UCAS

**Samohostowany silnik klasyfikacji tekstu**, który integrator wdraża u swoich klientów
pod własną marką. Klasyfikuje zgłoszenia, maile i dokumenty kaskadą warstw — od tanich
reguł, przez ML, po lokalny LLM — zatrzymując się na pierwszej pewnej odpowiedzi.

## Dlaczego warto to odsprzedawać (dla integratora)

- **Nowy strumień przychodu** bez budowania AI od zera — gotowy produkt do white-label.
- **Argument prywatności** — działa 100% on-prem (RODO). Otwiera klientów regulowanych
  (banki, zdrowie, kancelarie, sektor publiczny), którzy odrzucają chmurowe API.
- **Niski koszt operacyjny** — ~90% ruchu obsługują tanie warstwy, LLM tylko dla trudnych.
- **Szybkie wdrożenie** — gotowe demo „pod klucz" i skrypty; pierwszy działający
  kategoryzator w godziny, nie tygodnie.
- **Wsparcie techniczne** producenta (L2) — Ty sprzedajesz i utrzymujesz relację, my
  trzymamy warstwę techniczną.

## Co dostaje klient końcowy

| Funkcja | Korzyść |
|---|---|
| Kaskada Tags → XGBoost → LLM | Niski koszt, niskie opóźnienie |
| Lokalny LLM (Ollama) | Dane nie opuszczają firmy (RODO) |
| Human-in-the-Loop + webhooki | Kontrola nad trudnymi przypadkami, ślad audytowy |
| Kuracja jakości danych | Model nie degraduje się w czasie |
| Multi-tenant | Wiele zastosowań z jednego wdrożenia |
| Panel zarządzania | Trening i testy bez programisty |

## Typowe zastosowania

Routing zgłoszeń Helpdesk · triage maili · klasyfikacja dokumentów i reklamacji ·
moderacja treści · routing leadów / intencji.

## Model współpracy (skrót — szczegóły w `pricing-and-terms.md`)

- **Licencja platformy** (abonament miesięczny dla partnera),
- **Opłata wdrożeniowa** za uruchomienie u klienta partnera,
- **Rev-share** od kontraktów domkniętych na UCAS.

## Następny krok

15-minutowe demo na żywo (`demo/QUICKSTART.md`) na Twoich przykładowych danych.
Kontakt: **[TWÓJ KONTAKT]**

---

# UCAS — Partner one-pager (English, DRAFT)

## What UCAS is
A **self-hosted text-classification engine** that integrators deploy for their clients
under their own brand. It classifies tickets, emails and documents through a cascade of
layers — cheap rules, then ML, then a local LLM — stopping at the first confident answer.

## Why resell it (for the integrator)
- **New revenue stream** without building AI from scratch — ready for white-label.
- **Privacy angle** — runs 100% on-prem (GDPR); unlocks regulated clients who reject cloud APIs.
- **Low running cost** — ~90% of traffic handled by cheap layers; the LLM only fires on hard cases.
- **Fast deployment** — turnkey demo and scripts; first working categorizer in hours.
- **Vendor L2 support** — you own the sales relationship, we own the technical layer.

## What the end client gets
Cascade (Tags → XGBoost → LLM), local LLM (data stays in-house), Human-in-the-Loop +
webhooks, automatic data-quality curation, multi-tenant, no-code management dashboard.

## Engagement model (see `pricing-and-terms.md`)
Platform license (partner subscription) + per-deployment fee + revenue share.

## Next step
A 15-minute live demo (`demo/QUICKSTART.md`) on your sample data. Contact: **[YOUR CONTACT]**
