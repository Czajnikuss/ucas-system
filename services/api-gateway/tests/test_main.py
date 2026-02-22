import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from main import app

client = TestClient(app)

def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "UCAS API Gateway"
    assert response.json()["routing"] == "dynamic"

@patch("main.redis_client")
@patch("httpx.AsyncClient.get")
def test_health_check_healthy(mock_get, mock_redis):
    # Mock Redis ping
    mock_redis.ping.return_value = True
    
    # Mock Orchestrator /health response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_get.return_value = mock_response
    
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    
    assert data["status"] == "healthy"
    assert data["services"]["redis"] == "healthy"
    assert data["services"]["orchestrator"] == "healthy"

@patch("httpx.AsyncClient.request")
def test_gateway_route_proxy(mock_request):
    mock_target_response = MagicMock()
    mock_target_response.status_code = 201
    mock_target_response.content = b'{"status": "created"}'
    mock_target_response.headers = {"Content-Type": "application/json"}
    
    mock_request.return_value = mock_target_response
    
    payload = {"name": "TestCategorizer"}
    response = client.post("/api/v1/categorizers", json=payload)
    
    assert response.status_code == 201
    assert response.json() == {"status": "created"}
    
    # Weryfikacja czy żądanie zostało przekazane bez nagłówka host
    args, kwargs = mock_request.call_args
    assert kwargs["method"] == "POST"
    assert kwargs["url"] == "http://orchestrator:8001/api/v1/categorizers"
    assert "host" not in kwargs["headers"]

@patch("httpx.AsyncClient.request")
def test_gateway_route_unreachable(mock_request):
    import httpx
    # Symulacja padu Orchestratora
    mock_request.side_effect = httpx.RequestError("Connection failed")
    
    response = client.get("/any/random/path")
    
    assert response.status_code == 503
    assert "Target service unreachable" in response.json()["detail"]