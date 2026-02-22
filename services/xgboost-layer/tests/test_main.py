import pytest
from fastapi.testclient import TestClient
from main import app, models_cache

client = TestClient(app)

def test_train_and_cache():
    models_cache.clear()
    payload = {
        "categorizer_id": "test-cat",
        "training_data": [{"text": "abc", "category": "A"}]
    }
    response = client.post("/train", json=payload)
    assert response.status_code == 200
    assert "test-cat" in models_cache
    
def test_classify_no_model():
    models_cache.clear()
    payload = {
        "categorizer_id": "missing-cat",
        "text": "test",
        "embedding": [0.1, 0.2]
    }
    response = client.post("/classify", json=payload)
    assert response.status_code == 404