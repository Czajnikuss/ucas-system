#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_samples.py — etap GENERACJI w pętli samodoskonalenia danych UCAS.

Over-produkuje próbki treningowe per kategoria przez dowolny endpoint zgodny z OpenAI
(np. LM Studio, Ollama `/v1`, OpenAI), a następnie (opcjonalnie) przepuszcza je przez
kurator evaluatora (`/curate_pool`), który metryką k-NN label-agreement usuwa błędny/
dwuznaczny ogon i near-duplikaty, ZACHOWUJĄC różnorodność.

Tylko biblioteka standardowa (urllib + json) — bez zależności, bez numpy na hoście.
Cała część wektorowa dzieje się w kontenerze evaluatora.

Różnorodność: rotujemy podtematy per wywołanie i podbijamy temperaturę gdy model zaczyna
się powtarzać; `--seed-pool` pozwala akumulować (top-up) z wcześniejszej puli.

Pełna pętla:
    python scripts/generate_samples.py --spec scripts/helpdesk_spec.json \\
        --endpoint http://localhost:1234/v1 --model qwopus3.5-9b-v3 \\
        --n 300 --out pool.json --curate-url http://localhost:8060 --curated-out curated.json

Spec (JSON): patrz scripts/helpdesk_spec.json
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request

# Windows: konsola cp1252 nie koduje polskich znakow w print() -> wymuszamy UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _post_json(url: str, payload: dict, timeout: float = 120.0, headers: dict | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8")
    hdr = {"Content-Type": "application/json"}
    if headers:
        hdr.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdr, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _extract_json(text: str):
    """Wyciąga obiekt/tablicę JSON z odpowiedzi modelu (toleruje ogrodzenia ```)."""
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            return None
    return None


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t.strip().lower())


def generate_for_category(endpoint, model, category, subtopics, language, domain,
                          count, batch, temperature, seed_texts=None):
    """Woła model w paczkach aż uzbiera `count` unikalnych próbek. Rotuje podtematy i podbija
    temperaturę gdy model się powtarza. Może wystartować od `seed_texts` (akumulacja)."""
    url = endpoint.rstrip("/") + "/chat/completions"
    seen = set()
    samples = []
    for t in (seed_texts or []):
        k = _norm(t)
        if len(t.strip()) >= 12 and k not in seen:
            seen.add(k)
            samples.append(t.strip())

    subs = subtopics or [category]
    system = (
        f"Jesteś generatorem syntetycznych danych treningowych ({domain}, język {language}). "
        f"Tworzysz realistyczne, RÓŻNORODNE zgłoszenia jednej kategorii. Zwracasz wyłącznie JSON."
    )

    attempt = 0
    max_attempts = max(20, (count // max(1, batch)) * 4)
    stall = 0
    temp = temperature
    while len(samples) < count and attempt < max_attempts:
        # Rotacja okna podtematow -> kazde wywolanie eksploruje inny obszar.
        start = (attempt * 3) % len(subs)
        win = subs[start:start + 3] or subs[:3]
        subtopic_hint = "Skup się na podtematach: " + "; ".join(win) + "."
        user = (
            f'Wygeneruj {batch} różnych, realistycznych zgłoszeń kategorii "{category}". '
            f"{subtopic_hint} "
            "Zróżnicuj długość (5-30 słów), ton (sfrustrowany, neutralny, uprzejmy, formalny, potoczny) "
            "i szczegóły (nazwy, numery, działy). Pierwsza osoba. NIE powtarzaj zgłoszeń z wcześniejszych "
            'odpowiedzi. Zwróć WYŁĄCZNIE JSON: {"samples": ["...", "...", ...]}'
        )
        before = len(samples)
        try:
            resp = _post_json(url, {
                "model": model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "temperature": round(temp, 2),
            }, timeout=180.0)
            content = resp["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"   ! [{category}] błąd wywołania: {e}", file=sys.stderr)
            time.sleep(1.0)
            attempt += 1
            continue

        parsed = _extract_json(content)
        items = []
        if isinstance(parsed, dict):
            items = parsed.get("samples") or parsed.get("texts") or []
        elif isinstance(parsed, list):
            items = parsed

        for it in items:
            txt = (it.get("text") if isinstance(it, dict) else it)
            if not isinstance(txt, str):
                continue
            txt = txt.strip()
            k = _norm(txt)
            if len(txt) >= 12 and k not in seen:
                seen.add(k)
                samples.append(txt)

        attempt += 1
        if len(samples) == before:
            stall += 1
            temp = min(1.25, temp + 0.07)   # podbij roznorodnosc gdy utyka
        else:
            stall = 0
        print(f"   [{category}] {len(samples)}/{count} (temp={temp:.2f})")
        if stall >= 6:   # twardy bezpiecznik na nieuleczalne powtarzanie
            print(f"   [{category}] stop (powtarzanie sie modelu)")
            break
    return samples[:count]


def main():
    ap = argparse.ArgumentParser(description="Over-generacja + opcjonalna kuracja danych UCAS")
    ap.add_argument("--spec", required=True, help="Plik JSON ze specyfikacją kategorii/podtematów")
    ap.add_argument("--endpoint", default="http://localhost:11434/v1", help="Bazowy URL OpenAI-compatible (LM Studio / Ollama /v1)")
    ap.add_argument("--model", default="local-model", help="Nazwa modelu na endpoincie")
    ap.add_argument("--n", type=int, default=150, help="Ile próbek na kategorię (over-generacja)")
    ap.add_argument("--batch", type=int, default=25, help="Ile próbek na jedno wywołanie LLM")
    ap.add_argument("--temperature", type=float, default=0.9)
    ap.add_argument("--seed-pool", default=None, help="Istniejąca pula JSON do akumulacji (top-up)")
    ap.add_argument("--out", default="pool.json", help="Plik wyjściowy puli (przed kuracją)")
    ap.add_argument("--curate-url", default=None, help="Jeśli podany, POST puli do evaluatora (np. http://localhost:8060)")
    ap.add_argument("--curated-out", default="curated.json", help="Plik wyjściowy po kuracji")
    ap.add_argument("--min-quality", type=float, default=0.25)
    ap.add_argument("--cap-per-category", type=int, default=None)
    args = ap.parse_args()

    spec = json.load(open(args.spec, encoding="utf-8"))
    language = spec.get("language", "polski")
    domain = spec.get("domain", "zgłoszenia")
    categories = spec["categories"]

    seed_by_cat = {}
    if args.seed_pool and os.path.exists(args.seed_pool):
        sp = json.load(open(args.seed_pool, encoding="utf-8"))
        for d in sp.get("training_data", []):
            seed_by_cat.setdefault(d["category"], []).append(d["text"])
        print(f"Seed-pool: {sum(len(v) for v in seed_by_cat.values())} próbek z {args.seed_pool}")

    pool = []
    for category, subtopics in categories.items():
        print(f"== Generuję kategorię: {category} ==")
        texts = generate_for_category(args.endpoint, args.model, category, subtopics or [],
                                      language, domain, args.n, args.batch, args.temperature,
                                      seed_texts=seed_by_cat.get(category))
        pool.extend({"text": t, "category": category} for t in texts)

    pool_doc = {
        "name": spec.get("name", "Generated-Categorizer"),
        "description": spec.get("description", "Synthetic over-generated pool (pre-curation)."),
        "layers": spec.get("layers", ["tags", "xgboost", "llm", "hil"]),
        "fallback_category": spec.get("fallback_category", "Inne"),
        "hil_config": spec.get("hil_config", {"enabled": True, "tags_threshold": 0.7, "xgboost_threshold": 0.6, "llm_threshold": 0.8}),
        "training_data": pool,
    }
    json.dump(pool_doc, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nPula: {len(pool)} próbek -> {args.out}")

    if args.curate_url:
        print("Kuracja przez evaluator /curate_pool ...")
        body = {"training_data": pool, "min_quality": args.min_quality, "dup_threshold": 0.97}
        if args.cap_per_category:
            body["cap_per_category"] = args.cap_per_category
        res = _post_json(args.curate_url.rstrip("/") + "/curate_pool", body, timeout=600.0)
        curated_doc = dict(pool_doc)
        curated_doc["training_data"] = res.get("curated", [])
        curated_doc["description"] = spec.get("description", "Curated dataset (k-NN quality + dedup).")
        json.dump(curated_doc, open(args.curated_out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"Po kuracji: in={res.get('input_count')} kept={res.get('kept_count')} "
              f"drop_lowq={res.get('dropped_low_quality')} drop_dup={res.get('dropped_duplicates')} "
              f"capped={res.get('capped')} avg_q={res.get('avg_quality_kept'):.3f} -> {args.curated_out}")


if __name__ == "__main__":
    main()
