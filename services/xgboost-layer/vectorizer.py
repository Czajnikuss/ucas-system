import numpy as np
from typing import List, Tuple, Any

class VectorizationConfig:
    def __init__(
        self,
        header_pct: float = 0.25,
        body_start_pct: float = 0.15,
        body_end_pct: float = 0.85,
        footer_pct: float = 0.25,
        short_text_threshold: int = 15,
        vector_size: int = 100
    ):
        self.header_pct = header_pct
        self.body_start_pct = body_start_pct
        self.body_end_pct = body_end_pct
        self.footer_pct = footer_pct
        self.short_text_threshold = short_text_threshold
        self.vector_size = vector_size

def extract_region_vectors(tokens: List[str], w2v_model: Any, vector_size: int) -> Tuple[np.ndarray, np.ndarray]:
    vectors = [w2v_model.wv[t] for t in tokens if t in w2v_model.wv]
    
    if not vectors:
        return np.zeros(vector_size), np.zeros(vector_size)
    
    vec_array = np.array(vectors)
    return np.mean(vec_array, axis=0), np.max(vec_array, axis=0)

def text_to_regional_vector(
    tokens: List[str], 
    w2v_model: Any, 
    config: VectorizationConfig = VectorizationConfig()
) -> np.ndarray:
    n_tokens = len(tokens)
    
    if n_tokens == 0:
        return np.zeros(config.vector_size * 8)
        
    w_mean, w_max = extract_region_vectors(tokens, w2v_model, config.vector_size)
    
    if n_tokens < config.short_text_threshold:
        return np.concatenate([w_mean, w_max, w_mean, w_max, w_mean, w_max, w_mean, w_max])
        
    h_end = max(1, int(n_tokens * config.header_pct))
    b_start = int(n_tokens * config.body_start_pct)
    b_end = int(n_tokens * config.body_end_pct)
    f_start = int(n_tokens * (1.0 - config.footer_pct))
    
    header_tokens = tokens[:h_end]
    body_tokens = tokens[b_start:b_end]
    footer_tokens = tokens[f_start:]
    
    h_mean, h_max = extract_region_vectors(header_tokens, w2v_model, config.vector_size)
    b_mean, b_max = extract_region_vectors(body_tokens, w2v_model, config.vector_size)
    f_mean, f_max = extract_region_vectors(footer_tokens, w2v_model, config.vector_size)
    
    return np.concatenate([w_mean, w_max, h_mean, h_max, b_mean, b_max, f_mean, f_max])