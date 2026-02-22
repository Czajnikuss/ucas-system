import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from main import app

client = TestClient(app)

@patch("main.get_db")
def test_inject_document(mock_get_db):
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db
    
    mock_result = MagicMock()
    mock_result.fetchone.return_value = ["mocked-uuid"]
    mock_db.execute.return_value = mock_result
    
    payload = {
        "categorizer_id": "cat-1",
        "text": "Zepsuty traktor",
        "category": "reklamacja",
        "embedding": [0.1, 0.5, 0.9]
    }
    
    response = client.post("/inject", json=payload)
    assert response.status_code == 200
    assert response.json()["inserted_id"] == "mocked-uuid"
    assert mock_db.execute.called