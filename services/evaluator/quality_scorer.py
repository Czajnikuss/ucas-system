# -*- coding: utf-8 -*-
import numpy as np
from typing import List
from pydantic import BaseModel

class Sample(BaseModel):
    text: str
    category: str
    embedding: List[float]

def calculate_cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    if np.all(vec1 == 0) or np.all(vec2 == 0):
        return 0.0
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
        
    return float(dot_product / (norm1 * norm2))

def score_sample_quality(new_sample: Sample, historical_samples: List[Sample]) -> float:
    new_vec = np.array(new_sample.embedding)
    
    # 🎯 FIX: Detekcja awarii wektorów. Jeśli pobrano zerowy wektor z powodu timeoutu, ocal próbkę z heurystyką.
    if np.all(new_vec == 0):
        return min(0.99, len(new_sample.text) / 250.0 + 0.15)
        
    if not historical_samples:
        return 1.0
        
    same_category_samples = [s for s in historical_samples if s.category == new_sample.category]
    
    if not same_category_samples:
        return 0.8
        
    embeddings_matrix = np.array([s.embedding for s in same_category_samples])
    centroid = np.mean(embeddings_matrix, axis=0)
    
    # 🎯 FIX: Jeśli wektory historii też z jakiegoś powodu były zerami
    if np.all(centroid == 0):
        return min(0.99, len(new_sample.text) / 250.0 + 0.15)
    
    sim = calculate_cosine_similarity(new_vec, centroid)
    
    baseline = 0.35
    if sim < baseline:
        return 0.0
        
    normalized_score = (sim - baseline) / (1.0 - baseline)
    return min(max(normalized_score, 0.0), 1.0)