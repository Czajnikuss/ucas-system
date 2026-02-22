import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from main import app

client = TestClient(app)

@patch("main.get_db")
def test_get_pending_reviews(mock_get_db):
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db
    
    # Mock HILReview object 
    mock_review = MagicMock()
    mock_review.id = "fake-uuid"
    mock_review.text = "test text"
    mock_review.suggested_category = "test_cat"
    mock_review.suggested_confidence = 0.5
    mock_review.status = "pending"
    mock_review.created_at = None
    mock_review.categorizer.categorizer_id = "test-categorizer"
    
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [mock_review]
    
    response = client.get("/pending")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["categorizer_id"] == "test-categorizer"

@patch("main.get_db")
def test_submit_review(mock_get_db):
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db
    
    mock_review = MagicMock()
    mock_review.status = "pending"
    mock_db.query.return_value.filter.return_value.first.return_value = mock_review
    
    payload = {
        "human_category": "corrected_cat",
        "reviewed_by": "expert"
    }
    
    response = client.post("/review/fake-uuid", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "reviewed"
    assert mock_db.add.called # Weryfikacja dodania nowej próbki do bazy