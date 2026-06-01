# scripts/

Skrypty pomocnicze i narzędzia danych UCAS.

## Pętla samodoskonalenia danych (over-generacja → kuracja → trening)

Idea: pozwolić systemowi **wybrać najlepsze dane**. Najpierw LLM **over-produkuje** dużo
kandydatów, potem **kurator** (metryka k-NN label-agreement w evaluatorze) usuwa błędny/
dwuznaczny ogon i near-duplikaty, **zachowując różnorodność** (cap przez farthest-point
sampling — nie zwijamy do centroidu). Wykurowany zbiór idzie do `/train`.

```
  generate_samples.py            evaluator /curate_pool              /train
  (LLM over-generuje)   ─────▶   (k-NN quality + dedup +    ─────▶   (tags/xgboost/llm)
   pool.json                      diversity cap)  curated.json
```

### 1. Generacja + kuracja (jedna komenda)

`generate_samples.py` używa tylko biblioteki standardowej (urllib) — **bez zależności na
hoście**. Cała część wektorowa dzieje się w kontenerze evaluatora. Działa z dowolnym
endpointem zgodnym z OpenAI (LM Studio, Ollama `/v1`, OpenAI).

```powershell
# LM Studio (większy model) jako generator, kuracja przez lokalny evaluator:
python scripts/generate_samples.py `
  --spec scripts/helpdesk_spec.json `
  --endpoint http://192.168.0.164:1234/v1 --model local-model `
  --n 150 --out pool.json `
  --curate-url http://localhost:8060 --curated-out curated.json

# albo lokalnie przez Ollama (qwen2.5):
python scripts/generate_samples.py --spec scripts/helpdesk_spec.json `
  --endpoint http://localhost:11434/v1 --model qwen2.5:3b --n 120 `
  --curate-url http://localhost:8060
```

Parametry kuracji: `--min-quality 0.25` (próg odcięcia k-NN), `--cap-per-category N`
(limit z zachowaniem różnorodności). `--spec` to definicja kategorii i podtematów
(patrz `helpdesk_spec.json`).

### 2. Sama kuracja istniejącej puli

Kurator to endpoint evaluatora — można go wołać wprost:

```powershell
$body = @{ training_data = (Get-Content demo/helpdesk_demo.json -Raw -Encoding UTF8 | ConvertFrom-Json).training_data
           min_quality = 0.25; dup_threshold = 0.97 } | ConvertTo-Json -Depth 6
Invoke-RestMethod -Uri http://localhost:8060/curate_pool -Method Post `
  -Body ([Text.Encoding]::UTF8.GetBytes($body)) -ContentType "application/json; charset=utf-8"
```

Zwraca raport (`input_count`, `kept_count`, `dropped_low_quality`, `dropped_duplicates`,
`capped`, `avg_quality_kept`, `per_category`) oraz `curated` (gotowe do `/train`).

### 3. Trening na wykurowanym zbiorze

```powershell
$b = Get-Content curated.json -Raw -Encoding UTF8
Invoke-RestMethod -Uri http://localhost:8000/train -Method Post `
  -Body ([Text.Encoding]::UTF8.GetBytes($b)) -ContentType "application/json; charset=utf-8"
```

## Pozostałe skrypty
- `test.ps1`, `test_e2e.ps1`, `test_xgb_800.ps1`, `webhook_test.ps1` — testy E2E/warstw.
- `inventory.ps1`, `delete_all_categorizers.ps1` — narzędzia dev.
- `generate_docs.py` — generacja inwentarza dokumentacji.
