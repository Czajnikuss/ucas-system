import pytest
import numpy as np
from vectorizer import VectorizationConfig, text_to_regional_vector

class MockW2V:
    class MockWV:
        def __contains__(self, item):
            return item.startswith("known")
            
        def __getitem__(self, item):
            if item == "known_1":
                return np.ones(10)
            elif item == "known_2":
                return np.full(10, 2.0)
            return np.zeros(10)
            
    def __init__(self):
        self.wv = self.MockWV()

def test_empty_tokens():
    model = MockW2V()
    config = VectorizationConfig(vector_size=10)
    result = text_to_regional_vector([], model, config)
    
    assert len(result) == 80
    assert np.all(result == 0)

def test_short_text_fallback():
    model = MockW2V()
    config = VectorizationConfig(short_text_threshold=15, vector_size=10)
    tokens = ["known_1", "known_2"]
    
    result = text_to_regional_vector(tokens, model, config)
    
    assert len(result) == 80
    # Pattern: [w_mean, w_max, h_mean, h_max, b_mean, b_max, f_mean, f_max]
    # Wartość mean to 1.5. Max to 2.0. Powielone na 4 strefy.
    assert np.all(result[0:10] == 1.5)  
    assert np.all(result[10:20] == 2.0) 
    assert np.all(result[20:30] == 1.5)
    assert np.all(result[40:50] == 1.5)

def test_long_text_zoning():
    model = MockW2V()
    config = VectorizationConfig(
        header_pct=0.25, 
        body_start_pct=0.15, body_end_pct=0.85, 
        footer_pct=0.25,
        short_text_threshold=5,
        vector_size=10
    )
    
    tokens = (
        ["known_1"] * 4 + 
        ["unknown"] * 12 + 
        ["known_2"] * 4
    )
    
    result = text_to_regional_vector(tokens, model, config)
    assert len(result) == 80
    
    # Global Mean / Max (indeksy 0-19)
    assert np.all(result[0:10] == 1.5)
    assert np.all(result[10:20] == 2.0)
    
    # Header - tylko known_1 (indeksy 20-39)
    assert np.all(result[20:30] == 1.0)
    assert np.all(result[30:40] == 1.0)
    
    # Body - known_1 i known_2 (indeksy 40-59)
    assert np.all(result[40:50] == 1.5)
    assert np.all(result[50:60] == 2.0)
    
    # Footer - tylko known_2 (indeksy 60-79)
    assert np.all(result[60:70] == 2.0)
    assert np.all(result[70:80] == 2.0)