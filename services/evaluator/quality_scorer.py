# -*- coding: utf-8 -*-
import numpy as np
from typing import List
from pydantic import BaseModel


class Sample(BaseModel):
    text: str
    category: str
    embedding: List[float]


def _heuristic(text: str) -> float:
    """Awaryjna ocena gdy brak użytecznego wektora (np. timeout embeddings-service)."""
    return min(0.99, len(text) / 250.0 + 0.15)


def score_sample_quality(new_sample: Sample, historical_samples: List[Sample], k: int = 10) -> float:
    """
    Jakość próbki = **zgodność etykiet w sąsiedztwie k-NN** w przestrzeni embeddingów
    (ważona podobieństwem). Dla każdej próbki patrzymy na jej k najbliższych sąsiadów spośród
    WSZYSTKICH kategorii i liczymy, jaka część (ważona similarity) ma tę samą etykietę.

    Dlaczego nie centroid: centroid karze różnorodność — próbka nietypowa, ale poprawna
    (np. inny podtemat tej samej kategorii) jest daleko od centroidu i dostaje niską ocenę.
    k-NN zachowuje takie próbki (mają sąsiadów tej samej klasy), a wyłapuje realnie błędne /
    dwuznaczne (sąsiedzi należą do innych klas).

    Zwraca wartość w [0.0, 1.0]: 1.0 = sąsiedztwo czyste, 0.0 = sami obcy (kandydat do archiwizacji).
    """
    new_vec = np.asarray(new_sample.embedding, dtype=np.float64)
    new_norm = np.linalg.norm(new_vec)
    if new_norm == 0:
        return _heuristic(new_sample.text)

    # Wykluczamy samą próbkę (po tekście) i próbki z zerowym wektorem.
    others = [
        s for s in historical_samples
        if s.text != new_sample.text and np.linalg.norm(np.asarray(s.embedding)) > 0
    ]
    if not others:
        return 1.0

    H = np.asarray([s.embedding for s in others], dtype=np.float64)      # (M, D)
    cats = np.asarray([s.category for s in others])
    H_norms = np.linalg.norm(H, axis=1)

    # Cosine similarity (evaluator nie żąda znormalizowanych wektorów, więc normalizujemy tu).
    sims = (H @ new_vec) / (H_norms * new_norm)

    kk = int(min(k, sims.shape[0]))
    top_idx = np.argpartition(-sims, kk - 1)[:kk]
    top_sims = np.clip(sims[top_idx], 0.0, None)   # ujemne podobieństwo nie głosuje
    top_cats = cats[top_idx]

    total_w = float(top_sims.sum())
    if total_w <= 0.0:
        return 0.0
    same_w = float(top_sims[top_cats == new_sample.category].sum())
    return same_w / total_w
