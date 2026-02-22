import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
from api.training import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)

@patch("api.training.get_db")
@patch("httpx.AsyncClient.post")
def test_train_success(mock_post, mock_get_db):
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db
    mock_db.query.return_value.filter.return_value.first.return_value = None

    mock_embed = MagicMock()
    mock_embed.status_code = 200
    mock_embed.json.return_value = {"embeddings": [[0.1, 0.2]]}
    
    mock_tags = MagicMock()
    mock_tags.status_code = 200
    mock_tags.json.return_value = {"status": "trained", "keywords": {}, "categories": ["A"]}
    
    mock_post.side_effect = [mock_embed, mock_tags]

    payload = {
        "name": "E2E Test",
        "training_data": [{"text": "text", "category": "A"}],
        "layers": ["tags"]
    }
    
    response = client.post("/train", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "trained"
    assert data["embeddings_generated"] is True
    assert "tags" in data["results"]