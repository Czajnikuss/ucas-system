from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
import redis
import json
import os
from typing import Optional, Dict

app = FastAPI(
    title="UCAS API Gateway",
    version="1.0.0",
    description="Universal Categorization as a Service - API Gateway",
    docs_url="/swagger"
)

# Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "ucas_redis_pass")
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://orchestrator:8001")

# Redis connection
try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=6379,
        password=REDIS_PASSWORD,
        decode_responses=True
    )
    redis_client.ping()
    print(f"✅ Connected to Redis at {REDIS_HOST}")
except Exception as e:
    print(f"⚠️  Redis connection failed: {e}")
    redis_client = None

# Health check
@app.get("/")
async def root():
    return {
        "service": "UCAS API Gateway",
        "status": "running",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    redis_status = "disconnected"
    orchestrator_status = "unknown"
    
    # Test Redis
    if redis_client:
        try:
            redis_client.ping()
            redis_status = "healthy"
        except:
            redis_status = "unhealthy"
    
    # Test Orchestrator
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{ORCHESTRATOR_URL}/health", timeout=3.0)
            if response.status_code == 200:
                orch_data = response.json()
                orchestrator_status = orch_data.get("status", "unknown")
    except:
        orchestrator_status = "unreachable"
    
    overall_status = "healthy" if (redis_status == "healthy" and orchestrator_status == "healthy") else "degraded"
    
    return {
        "status": overall_status,
        "services": {
            "redis": redis_status,
            "orchestrator": orchestrator_status
        }
    }

# === CATEGORIZER ENDPOINTS (proxied to Orchestrator) ===

@app.post("/api/v1/categorizers/initialize")
async def initialize_categorizer(data: Dict):
    """Initialize a new categorizer"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{ORCHESTRATOR_URL}/internal/categorizers/initialize",
                json=data,
                timeout=60.0
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Orchestrator error: {str(e)}")

@app.get("/api/v1/categorizers")
async def list_categorizers():
    """List all categorizers"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{ORCHESTRATOR_URL}/internal/categorizers",
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Orchestrator error: {str(e)}")

@app.get("/api/v1/categorizers/{categorizer_id}/status")
async def get_categorizer_status(categorizer_id: str):
    """Get categorizer status"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{ORCHESTRATOR_URL}/internal/categorizers/{categorizer_id}/status",
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Categorizer not found")
        raise HTTPException(status_code=500, detail=f"Orchestrator error: {str(e)}")

# Test endpoint
@app.get("/test/redis")
async def test_redis():
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis not available")
    
    redis_client.set("api_test", "Gateway is working!", ex=60)
    value = redis_client.get("api_test")
    
    return {
        "redis_connection": "OK",
        "test_value": value,
        "message": "Redis is working properly"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)